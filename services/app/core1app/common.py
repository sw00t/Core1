"""Shared plumbing: settings, JSON logs, Prometheus metrics, trace propagation, upstream calls."""
import json
import logging
import os
import secrets
import sys
import time
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest

SERVICE = os.environ.get("CORE1_SERVICE", "app")
VERSION = os.environ.get("APP_VERSION", "dev")
UNINSTRUMENTED = {"/metrics", "/healthz", "/livez"}
BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10)


def env_str(name, default):
    return os.environ.get(name, default)


def env_int(name, default):
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return int(default)


def env_float(name, default):
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return float(default)


# ---------------------------------------------------------------- logging
class JsonFormatter(logging.Formatter):
    STANDARD = set(vars(logging.LogRecord("", 0, "", 0, "", (), None)).keys()) | {"message", "asctime"}

    def format(self, record):
        d = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created)) + ".%03dZ" % record.msecs,
            "level": record.levelname.lower(),
            "service": SERVICE,
            "msg": record.getMessage(),
        }
        for k, v in record.__dict__.items():
            if k not in self.STANDARD and not k.startswith("_"):
                d[k] = v
        if record.exc_info:
            d["exc"] = self.formatException(record.exc_info)
        return json.dumps(d, default=str)


def setup_logging():
    level = os.environ.get("LOG_LEVEL", "info").upper()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        lg = logging.getLogger(name)
        lg.handlers[:] = []
        lg.propagate = True
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


log = logging.getLogger("core1")

# ---------------------------------------------------------------- metrics
REQUESTS = Counter("http_requests_total", "HTTP requests served", ["method", "route", "status"])
LATENCY = Histogram("http_request_duration_seconds", "HTTP request latency", ["method", "route"], buckets=BUCKETS)
IN_FLIGHT = Gauge("http_requests_in_flight", "HTTP requests currently being served")
UPSTREAM = Counter("upstream_requests_total", "Calls to upstream services", ["upstream", "outcome"])
UPSTREAM_LATENCY = Histogram("upstream_request_duration_seconds", "Upstream call latency", ["upstream"], buckets=BUCKETS)
BUILD_INFO = Gauge("core1_build_info", "Build information", ["service", "version"])
BUILD_INFO.labels(SERVICE, VERSION).set(1)


# ---------------------------------------------------------------- tracing (W3C traceparent propagation)
def parse_traceparent(value):
    if value:
        parts = value.split("-")
        if len(parts) == 4 and len(parts[1]) == 32 and len(parts[2]) == 16:
            return parts[1]
    return None


def new_trace_id():
    return secrets.token_hex(16)


def make_traceparent(trace_id):
    return f"00-{trace_id}-{secrets.token_hex(8)}-01"


# ---------------------------------------------------------------- errors
class UpstreamError(Exception):
    def __init__(self, status, detail, upstream):
        super().__init__(detail)
        self.status = status
        self.detail = detail
        self.upstream = upstream


class HTTPError(Exception):
    def __init__(self, status, detail):
        super().__init__(detail)
        self.status = status
        self.detail = detail


# ---------------------------------------------------------------- app factory
def create_app(name, lifespan=None):
    @asynccontextmanager
    async def _lifespan(app):
        app.state.ready = True
        app.state.http = httpx.AsyncClient(limits=httpx.Limits(max_connections=200, max_keepalive_connections=50))
        log.info("service starting", extra={"version": VERSION, "app": name})
        try:
            if lifespan is None:
                yield
            else:
                async with lifespan(app):
                    yield
        finally:
            await app.state.http.aclose()
            log.info("service stopping")

    app = FastAPI(title=f"core1-{name}", version=VERSION, lifespan=_lifespan, docs_url=None, redoc_url=None)

    @app.middleware("http")
    async def instrument(request: Request, call_next):
        path = request.url.path
        if path in UNINSTRUMENTED:
            return await call_next(request)
        trace_id = parse_traceparent(request.headers.get("traceparent")) or new_trace_id()
        request.state.trace_id = trace_id
        IN_FLIGHT.inc()
        t0 = time.perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            response.headers["traceparent"] = make_traceparent(trace_id)
            return response
        finally:
            elapsed = time.perf_counter() - t0
            IN_FLIGHT.dec()
            route = getattr(request.scope.get("route"), "path", None) or "unmatched"
            REQUESTS.labels(request.method, route, str(status)).inc()
            LATENCY.labels(request.method, route).observe(elapsed)
            level = logging.INFO if status < 500 else logging.ERROR
            log.log(level, "request", extra={
                "method": request.method, "route": route, "path": path, "status": status,
                "duration_ms": round(elapsed * 1000, 1), "trace_id": trace_id,
                "client": request.client.host if request.client else None,
            })

    @app.exception_handler(UpstreamError)
    async def _upstream_error(request: Request, exc: UpstreamError):
        return JSONResponse({"error": exc.detail, "upstream": exc.upstream}, status_code=exc.status)

    @app.exception_handler(HTTPError)
    async def _http_error(request: Request, exc: HTTPError):
        return JSONResponse({"error": exc.detail}, status_code=exc.status)

    @app.get("/healthz")
    async def healthz():
        if getattr(app.state, "ready", False):
            return {"status": "ok", "service": name, "version": VERSION}
        return JSONResponse({"status": "not ready", "service": name}, status_code=503)

    @app.get("/livez")
    async def livez():
        return {"status": "alive"}

    @app.get("/metrics")
    async def metrics():
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    return app


# ---------------------------------------------------------------- upstream calls
async def call_upstream(client, upstream, method, url, *, timeout_ms, trace_id, json_body=None, ok_statuses=(200, 201)):
    """Call another service. Timeouts become 504, transport failures and 5xx become 502.
    4xx responses are returned to the caller unchanged so business errors (404, 409) pass through."""
    headers = {"traceparent": make_traceparent(trace_id)}
    t0 = time.perf_counter()
    try:
        resp = await client.request(method, url, json=json_body, headers=headers, timeout=timeout_ms / 1000.0)
    except httpx.TimeoutException:
        UPSTREAM.labels(upstream, "timeout").inc()
        log.error("upstream timeout", extra={"upstream": upstream, "timeout_ms": timeout_ms, "trace_id": trace_id})
        raise UpstreamError(504, f"{upstream} did not respond within {timeout_ms}ms", upstream)
    except httpx.HTTPError as exc:
        UPSTREAM.labels(upstream, "error").inc()
        log.error("upstream unreachable", extra={"upstream": upstream, "error": exc.__class__.__name__, "trace_id": trace_id})
        raise UpstreamError(502, f"{upstream} unreachable", upstream)
    finally:
        UPSTREAM_LATENCY.labels(upstream).observe(time.perf_counter() - t0)
    if resp.status_code >= 500:
        UPSTREAM.labels(upstream, "5xx").inc()
        log.error("upstream error", extra={"upstream": upstream, "status": resp.status_code, "trace_id": trace_id})
        raise UpstreamError(502, f"{upstream} returned {resp.status_code}", upstream)
    UPSTREAM.labels(upstream, "ok" if resp.status_code in ok_statuses else "4xx").inc()
    return resp

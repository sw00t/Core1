"""Synthetic traffic against the gateway at LOAD_RPS requests per second.
Mix: 60% activation orders (app, web, retail channels), 30% order status reads, 10% plan catalogue reads."""
import asyncio
import collections
import logging
import random
import time
from contextlib import asynccontextmanager

import httpx
from prometheus_client import Counter, Histogram

from .common import BUCKETS, create_app, env_float, env_str, log

TARGET_URL = env_str("TARGET_URL", "http://gateway:8080")
LOAD_RPS = env_float("LOAD_RPS", 40)
MAX_IN_FLIGHT = 150
PLANS = [f"PLAN-{n:03d}" for n in range(1, 13)]
CHANNELS = ["app", "app", "web", "retail"]

REQS = Counter("loadgen_requests_total", "Requests sent by the load generator", ["action", "outcome"])
LAT = Histogram("loadgen_request_duration_seconds", "End-to-end latency seen by the load generator", ["action"], buckets=BUCKETS)

recent_ids = collections.deque(maxlen=500)
stats = collections.Counter()


async def one(client, sem):
    r = random.random()
    if r < 0.6 or not recent_ids:
        action, method, path, body = "activate", "POST", "/api/orders", {"plan": random.choice(PLANS), "qty": 1, "channel": random.choice(CHANNELS)}
    elif r < 0.9:
        action, method, path, body = "order_status", "GET", f"/api/orders/{random.choice(recent_ids)}", None
    else:
        action, method, path, body = "list_plans", "GET", "/api/plans", None
    async with sem:
        t0 = time.perf_counter()
        try:
            resp = await client.request(method, TARGET_URL + path, json=body, timeout=5.0)
            outcome = "ok" if resp.status_code < 400 else ("4xx" if resp.status_code < 500 else "5xx")
            if action == "activate" and resp.status_code == 201:
                try:
                    recent_ids.append(resp.json()["id"])
                except Exception:  # noqa: BLE001
                    pass
        except httpx.TimeoutException:
            outcome = "timeout"
        except httpx.HTTPError:
            outcome = "error"
        LAT.labels(action).observe(time.perf_counter() - t0)
        REQS.labels(action, outcome).inc()
        stats[outcome] += 1


async def generator(app):
    sem = asyncio.Semaphore(MAX_IN_FLIGHT)
    interval = 1.0 / max(LOAD_RPS, 0.1)
    last_report = time.monotonic()
    async with httpx.AsyncClient(limits=httpx.Limits(max_connections=MAX_IN_FLIGHT)) as client:
        log.info("load generator started", extra={"target": TARGET_URL, "rps": LOAD_RPS})
        while True:
            asyncio.create_task(one(client, sem))
            await asyncio.sleep(interval * random.uniform(0.5, 1.5))
            now = time.monotonic()
            if now - last_report >= 30:
                total = sum(stats.values())
                log.info("activation load summary", extra={"window_s": 30, "requests": total, **{f"n_{k}": v for k, v in stats.items()},
                                                "error_pct": round(100.0 * (stats["5xx"] + stats["timeout"] + stats["error"]) / total, 1) if total else 0})
                stats.clear()
                last_report = now


@asynccontextmanager
async def lifespan(app):
    task = asyncio.create_task(generator(app))
    try:
        yield
    finally:
        task.cancel()


app = create_app("loadgen", lifespan=lifespan)

"""Orders: activation orders. Reserves a SIM and number with inventory, then records the order in Postgres.

DB_DSN=memory:// swaps in an in-memory store for local development and tests.
DB_QUERY_COST_MS adds a fixed pg_sleep per query so pool pressure is visible at lab scale.
"""
import asyncio
import itertools
import logging
from contextlib import asynccontextmanager

from fastapi import Request
from prometheus_client import Counter, Gauge
from pydantic import BaseModel, Field

from .common import HTTPError, call_upstream, create_app, env_int, env_str, log

DB_DSN = env_str("DB_DSN", "memory://")
DB_POOL_MIN = env_int("DB_POOL_MIN", 1)
DB_POOL_MAX = env_int("DB_POOL_MAX", 10)
DB_POOL_ACQUIRE_TIMEOUT_MS = env_int("DB_POOL_ACQUIRE_TIMEOUT_MS", 1000)
DB_QUERY_COST_MS = env_int("DB_QUERY_COST_MS", 100)
INVENTORY_URL = env_str("INVENTORY_URL", "http://inventory:8080")
INVENTORY_TIMEOUT_MS = env_int("INVENTORY_TIMEOUT_MS", 800)

POOL_MAX = Gauge("db_pool_max_connections", "Configured maximum pool size")
POOL_IN_USE = Gauge("db_pool_connections_in_use", "Pool connections currently checked out")
POOL_TIMEOUTS = Counter("db_pool_acquire_timeouts_total", "Requests that timed out waiting for a connection")
DB_ERRORS = Counter("db_errors_total", "Database errors")
POOL_MAX.set(DB_POOL_MAX)


class NewOrder(BaseModel):
    plan: str = Field(min_length=1, max_length=64)
    qty: int = Field(ge=1, le=100)
    channel: str = Field(default="app", max_length=32)


class MemoryStore:
    def __init__(self):
        self.rows = {}
        self.ids = itertools.count(1)
        self.sem = asyncio.Semaphore(DB_POOL_MAX)

    async def start(self):
        return True

    async def _cost(self):
        if DB_QUERY_COST_MS:
            await asyncio.sleep(DB_QUERY_COST_MS / 1000.0)

    async def _acquire(self):
        try:
            await asyncio.wait_for(self.sem.acquire(), timeout=DB_POOL_ACQUIRE_TIMEOUT_MS / 1000.0)
        except asyncio.TimeoutError:
            raise
        POOL_IN_USE.set(DB_POOL_MAX - self.sem._value)

    def _release(self):
        self.sem.release()
        POOL_IN_USE.set(DB_POOL_MAX - self.sem._value)

    async def create_order(self, plan, qty, iccid, msisdn, channel):
        await self._acquire()
        try:
            await self._cost()
            oid = next(self.ids)
            self.rows[oid] = {"id": oid, "plan": plan, "qty": qty, "iccid": iccid, "msisdn": msisdn, "channel": channel, "status": "activated"}
            return self.rows[oid]
        finally:
            self._release()

    async def get_order(self, oid):
        await self._acquire()
        try:
            await self._cost()
            return self.rows.get(oid)
        finally:
            self._release()

    async def recent_ids(self, n):
        return list(self.rows.keys())[-n:]


class PgStore:
    def __init__(self, dsn):
        self.dsn = dsn
        self.pool = None

    async def start(self):
        import asyncpg
        self.pool = await asyncpg.create_pool(self.dsn, min_size=DB_POOL_MIN, max_size=DB_POOL_MAX,
                                              command_timeout=10)
        async with self.pool.acquire() as conn:
            await conn.execute(
                "CREATE TABLE IF NOT EXISTS orders (id BIGSERIAL PRIMARY KEY, plan TEXT NOT NULL, "
                "qty INT NOT NULL, status TEXT NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now())")
            await conn.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS iccid TEXT, ADD COLUMN IF NOT EXISTS msisdn TEXT, "
                               "ADD COLUMN IF NOT EXISTS channel TEXT")
        return True

    def _gauge(self):
        if self.pool is not None:
            POOL_IN_USE.set(self.pool.get_size() - self.pool.get_idle_size())

    async def _cost(self, conn):
        if DB_QUERY_COST_MS:
            await conn.execute("SELECT pg_sleep($1)", DB_QUERY_COST_MS / 1000.0)

    async def create_order(self, plan, qty, iccid, msisdn, channel):
        async with self.pool.acquire(timeout=DB_POOL_ACQUIRE_TIMEOUT_MS / 1000.0) as conn:
            self._gauge()
            try:
                await self._cost(conn)
                row = await conn.fetchrow(
                    "INSERT INTO orders (plan, qty, iccid, msisdn, channel, status) VALUES ($1, $2, $3, $4, $5, 'activated') "
                    "RETURNING id, plan, qty, iccid, msisdn, channel, status", plan, qty, iccid, msisdn, channel)
                return dict(row)
            finally:
                self._gauge()

    async def get_order(self, oid):
        async with self.pool.acquire(timeout=DB_POOL_ACQUIRE_TIMEOUT_MS / 1000.0) as conn:
            self._gauge()
            try:
                await self._cost(conn)
                row = await conn.fetchrow("SELECT id, plan, qty, iccid, msisdn, channel, status FROM orders WHERE id = $1", oid)
                return dict(row) if row else None
            finally:
                self._gauge()

    async def recent_ids(self, n):
        async with self.pool.acquire(timeout=DB_POOL_ACQUIRE_TIMEOUT_MS / 1000.0) as conn:
            rows = await conn.fetch("SELECT id FROM orders ORDER BY id DESC LIMIT $1", n)
            return [r["id"] for r in rows]


async def connect_with_retry(app, store):
    delay = 1
    while True:
        try:
            await store.start()
            app.state.ready = True
            log.info("database ready", extra={"pool_max": DB_POOL_MAX, "backend": "memory" if DB_DSN.startswith("memory") else "postgres"})
            return
        except Exception as exc:  # noqa: BLE001
            DB_ERRORS.inc()
            log.warning("database not ready, retrying", extra={"error": str(exc)[:200], "retry_in_s": delay})
            await asyncio.sleep(delay)
            delay = min(delay * 2, 10)


@asynccontextmanager
async def lifespan(app):
    app.state.ready = False
    app.state.store = MemoryStore() if DB_DSN.startswith("memory") else PgStore(DB_DSN)
    task = asyncio.create_task(connect_with_retry(app, app.state.store))
    try:
        yield
    finally:
        task.cancel()


app = create_app("orders", lifespan=lifespan)


def db_guard(coro):
    """Translate pool exhaustion and database errors into clear 5xx responses."""
    async def run():
        try:
            return await coro
        except asyncio.TimeoutError:
            POOL_TIMEOUTS.inc()
            log.error("timed out waiting for a database connection", extra={"pool_max": DB_POOL_MAX, "acquire_timeout_ms": DB_POOL_ACQUIRE_TIMEOUT_MS})
            raise HTTPError(503, "database connection pool exhausted")
        except HTTPError:
            raise
        except Exception as exc:  # noqa: BLE001
            DB_ERRORS.inc()
            log.error("database error", extra={"error": str(exc)[:200]})
            raise HTTPError(500, "database error")
    return run()


@app.post("/orders", status_code=201)
async def create_order(order: NewOrder, request: Request):
    if not request.app.state.ready:
        raise HTTPError(503, "database not ready")
    resp = await call_upstream(request.app.state.http, "inventory", "POST", f"{INVENTORY_URL}/reserve",
                               timeout_ms=INVENTORY_TIMEOUT_MS, trace_id=request.state.trace_id,
                               json_body={"plan": order.plan, "qty": order.qty}, ok_statuses=(200,))
    if resp.status_code >= 400:
        detail = (resp.json() or {}).get("error", "reservation rejected") if resp.content else "reservation rejected"
        raise HTTPError(resp.status_code, detail)
    res = resp.json()
    row = await db_guard(request.app.state.store.create_order(order.plan, order.qty, res.get("iccid"), res.get("msisdn"), order.channel))
    log.info("activation order created", extra={"order_id": row["id"], "plan": order.plan, "channel": order.channel,
                                               "iccid": row.get("iccid"), "msisdn": row.get("msisdn"), "trace_id": request.state.trace_id})
    return row


@app.get("/orders/recent")
async def recent(request: Request, n: int = 50):
    if not request.app.state.ready:
        raise HTTPError(503, "database not ready")
    ids = await db_guard(request.app.state.store.recent_ids(max(1, min(n, 500))))
    return {"ids": ids}


@app.get("/orders/{order_id}")
async def get_order(order_id: int, request: Request):
    if not request.app.state.ready:
        raise HTTPError(503, "database not ready")
    row = await db_guard(request.app.state.store.get_order(order_id))
    if row is None:
        raise HTTPError(404, "order not found")
    return row

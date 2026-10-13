"""Inventory: stock levels per SKU, reservations, periodic restock.

Also hosts a runtime fault switch (POST /admin/fault) used by the lab to simulate a slow or failing
dependency without any change in the config repo. It is per-pod and in-memory; a restart clears it.
"""
import asyncio
import random
from contextlib import asynccontextmanager

from fastapi import Request
from pydantic import BaseModel, Field

from .common import HTTPError, create_app, env_int, log

RESTOCK_INTERVAL_S = env_int("RESTOCK_INTERVAL_S", 60)
SKUS = [f"SKU-{n:04d}" for n in range(1, 25)]
STOCK = {sku: 100000 for sku in SKUS}
FAULT = {"latency_ms": 0, "error_rate": 0.0}


class Reservation(BaseModel):
    sku: str
    qty: int = Field(ge=1, le=100)


class Fault(BaseModel):
    latency_ms: int = Field(ge=0, le=30000, default=0)
    error_rate: float = Field(ge=0.0, le=1.0, default=0.0)


async def restock_loop():
    while True:
        await asyncio.sleep(RESTOCK_INTERVAL_S)
        for sku in SKUS:
            STOCK[sku] = max(STOCK[sku], 100000)


@asynccontextmanager
async def lifespan(app):
    task = asyncio.create_task(restock_loop())
    try:
        yield
    finally:
        task.cancel()


app = create_app("inventory", lifespan=lifespan)


async def simulated_work():
    # a little real work, plus whatever the runtime fault switch adds
    await asyncio.sleep(random.uniform(0.003, 0.012))
    if FAULT["latency_ms"]:
        await asyncio.sleep(FAULT["latency_ms"] / 1000.0)
    if FAULT["error_rate"] and random.random() < FAULT["error_rate"]:
        raise HTTPError(500, "internal error")


@app.get("/stock")
async def stock(request: Request):
    await simulated_work()
    return {"items": [{"sku": s, "available": STOCK[s]} for s in SKUS]}


@app.get("/stock/{sku}")
async def stock_one(sku: str, request: Request):
    await simulated_work()
    if sku not in STOCK:
        raise HTTPError(404, "unknown sku")
    return {"sku": sku, "available": STOCK[sku]}


@app.post("/reserve")
async def reserve(res: Reservation, request: Request):
    await simulated_work()
    if res.sku not in STOCK:
        raise HTTPError(404, "unknown sku")
    if STOCK[res.sku] < res.qty:
        raise HTTPError(409, "insufficient stock")
    STOCK[res.sku] -= res.qty
    return {"sku": res.sku, "reserved": res.qty, "remaining": STOCK[res.sku]}


@app.get("/admin/fault")
async def get_fault():
    return FAULT


@app.post("/admin/fault")
async def set_fault(fault: Fault):
    FAULT["latency_ms"] = fault.latency_ms
    FAULT["error_rate"] = fault.error_rate
    log.debug("fault switch updated", extra={"latency_ms": fault.latency_ms, "error_rate": fault.error_rate})
    return FAULT

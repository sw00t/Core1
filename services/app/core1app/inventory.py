"""Inventory: SIM and number stock per plan code, reservations, periodic restock.

A reservation hands out an ICCID (SIM) and an MSISDN (number) for the plan. Identifiers are synthetic.

Also hosts a runtime fault switch (POST /admin/fault) used by the lab to simulate a slow or failing
dependency without any change in the config repo. It is per-pod and in-memory; a restart clears it.
"""
import asyncio
import itertools
import random
from contextlib import asynccontextmanager

from fastapi import Request
from pydantic import BaseModel, Field

from .common import HTTPError, create_app, env_int, log

RESTOCK_INTERVAL_S = env_int("RESTOCK_INTERVAL_S", 60)
PLANS = [f"PLAN-{n:03d}" for n in range(1, 13)]
STOCK = {plan: 100000 for plan in PLANS}
_serial = itertools.count(1)


def _next_identifiers():
    n = next(_serial)
    iccid = f"8901260{n:012d}"          # 19 digits, telecom MII 89 + synthetic
    msisdn = f"1206{(5550000 + n % 4000000):07d}"  # NANP, 206 area code, synthetic
    return iccid, msisdn
FAULT = {"latency_ms": 0, "error_rate": 0.0}


class Reservation(BaseModel):
    plan: str
    qty: int = Field(ge=1, le=100)


class Fault(BaseModel):
    latency_ms: int = Field(ge=0, le=30000, default=0)
    error_rate: float = Field(ge=0.0, le=1.0, default=0.0)


async def restock_loop():
    while True:
        await asyncio.sleep(RESTOCK_INTERVAL_S)
        for plan in PLANS:
            STOCK[plan] = max(STOCK[plan], 100000)


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
    return {"items": [{"plan": p, "sims_available": STOCK[p]} for p in PLANS]}


@app.get("/stock/{plan}")
async def stock_one(plan: str, request: Request):
    await simulated_work()
    if plan not in STOCK:
        raise HTTPError(404, "unknown plan")
    return {"plan": plan, "sims_available": STOCK[plan]}


@app.post("/reserve")
async def reserve(res: Reservation, request: Request):
    await simulated_work()
    if res.plan not in STOCK:
        raise HTTPError(404, "unknown plan")
    if STOCK[res.plan] < res.qty:
        raise HTTPError(409, "no SIM stock for plan")
    STOCK[res.plan] -= res.qty
    iccid, msisdn = _next_identifiers()
    return {"plan": res.plan, "reserved": res.qty, "remaining": STOCK[res.plan], "iccid": iccid, "msisdn": msisdn}


@app.get("/admin/fault")
async def get_fault():
    return FAULT


@app.post("/admin/fault")
async def set_fault(fault: Fault):
    FAULT["latency_ms"] = fault.latency_ms
    FAULT["error_rate"] = fault.error_rate
    log.debug("fault switch updated", extra={"latency_ms": fault.latency_ms, "error_rate": fault.error_rate})
    return FAULT

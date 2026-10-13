"""Gateway: the public edge. Validates requests and forwards to orders and inventory."""
from fastapi import Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .common import HTTPError, call_upstream, create_app, env_int, env_str

ORDERS_URL = env_str("ORDERS_URL", "http://orders:8080")
INVENTORY_URL = env_str("INVENTORY_URL", "http://inventory:8080")
UPSTREAM_TIMEOUT_MS = env_int("UPSTREAM_TIMEOUT_MS", 2000)

app = create_app("gateway")


class NewOrder(BaseModel):
    sku: str = Field(min_length=1, max_length=64)
    qty: int = Field(ge=1, le=100)


def passthrough(resp):
    return JSONResponse(resp.json() if resp.content else None, status_code=resp.status_code)


@app.get("/api/products")
async def products(request: Request):
    resp = await call_upstream(request.app.state.http, "inventory", "GET", f"{INVENTORY_URL}/stock",
                               timeout_ms=UPSTREAM_TIMEOUT_MS, trace_id=request.state.trace_id)
    return passthrough(resp)


@app.post("/api/orders", status_code=201)
async def create_order(order: NewOrder, request: Request):
    resp = await call_upstream(request.app.state.http, "orders", "POST", f"{ORDERS_URL}/orders",
                               timeout_ms=UPSTREAM_TIMEOUT_MS, trace_id=request.state.trace_id,
                               json_body=order.model_dump())
    return passthrough(resp)


@app.get("/api/orders/{order_id}")
async def get_order(order_id: str, request: Request):
    if not order_id.isdigit():
        raise HTTPError(400, "order id must be numeric")
    resp = await call_upstream(request.app.state.http, "orders", "GET", f"{ORDERS_URL}/orders/{order_id}",
                               timeout_ms=UPSTREAM_TIMEOUT_MS, trace_id=request.state.trace_id)
    return passthrough(resp)

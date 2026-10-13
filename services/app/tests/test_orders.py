import time

import httpx
from fastapi.testclient import TestClient

from core1app import orders


def inventory_ok(req):
    if req.url.path == "/reserve":
        return httpx.Response(200, json={"sku": "SKU-0001", "reserved": 1, "remaining": 9})
    return httpx.Response(500)


def wait_ready(c):
    for _ in range(50):
        if c.get("/healthz").status_code == 200:
            return
        time.sleep(0.05)
    raise AssertionError("orders never became ready")


def test_create_get_recent_with_memory_store():
    with TestClient(orders.app) as c:
        wait_ready(c)
        orders.app.state.http = httpx.AsyncClient(transport=httpx.MockTransport(inventory_ok))
        r = c.post("/orders", json={"sku": "SKU-0001", "qty": 1})
        assert r.status_code == 201
        oid = r.json()["id"]
        assert c.get(f"/orders/{oid}").json()["sku"] == "SKU-0001"
        assert c.get("/orders/999999").status_code == 404
        assert oid in c.get("/orders/recent").json()["ids"]


def test_inventory_rejection_is_passed_through():
    def inventory_409(req):
        return httpx.Response(409, json={"error": "insufficient stock"})

    with TestClient(orders.app) as c:
        wait_ready(c)
        orders.app.state.http = httpx.AsyncClient(transport=httpx.MockTransport(inventory_409))
        r = c.post("/orders", json={"sku": "SKU-0001", "qty": 1})
        assert r.status_code == 409 and r.json()["error"] == "insufficient stock"


def test_inventory_timeout_is_504():
    def slow(req):
        raise httpx.ReadTimeout("slow", request=req)

    with TestClient(orders.app) as c:
        wait_ready(c)
        orders.app.state.http = httpx.AsyncClient(transport=httpx.MockTransport(slow))
        assert c.post("/orders", json={"sku": "SKU-0001", "qty": 1}).status_code == 504

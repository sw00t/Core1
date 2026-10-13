import httpx
from fastapi.testclient import TestClient

from core1app import gateway


def mock_upstreams(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def test_create_and_get_order_pass_through():
    def handler(req):
        assert req.headers.get("traceparent", "").startswith("00-")
        if req.method == "POST" and req.url.path == "/orders":
            return httpx.Response(201, json={"id": 7, "sku": "SKU-0001", "qty": 2, "status": "confirmed"})
        if req.url.path == "/orders/7":
            return httpx.Response(200, json={"id": 7})
        if req.url.path == "/orders/8":
            return httpx.Response(404, json={"error": "order not found"})
        if req.url.path == "/stock":
            return httpx.Response(200, json={"items": []})
        return httpx.Response(500)

    with TestClient(gateway.app) as c:
        gateway.app.state.http = mock_upstreams(handler)
        r = c.post("/api/orders", json={"sku": "SKU-0001", "qty": 2})
        assert r.status_code == 201 and r.json()["id"] == 7
        assert c.get("/api/orders/7").status_code == 200
        assert c.get("/api/orders/8").status_code == 404
        assert c.get("/api/orders/abc").status_code == 400
        assert c.get("/api/products").status_code == 200
        assert c.post("/api/orders", json={"sku": "", "qty": 2}).status_code == 422


def test_upstream_failures_map_to_502_504():
    def handler(req):
        if req.url.path == "/stock":
            raise httpx.ReadTimeout("slow", request=req)
        return httpx.Response(503, json={"error": "down"})

    with TestClient(gateway.app) as c:
        gateway.app.state.http = mock_upstreams(handler)
        assert c.get("/api/products").status_code == 504
        r = c.post("/api/orders", json={"sku": "SKU-0001", "qty": 1})
        assert r.status_code == 502 and r.json()["upstream"] == "orders"

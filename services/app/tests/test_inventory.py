import time

from fastapi.testclient import TestClient

from core1app import inventory


def client():
    return TestClient(inventory.app)


def test_stock_and_reserve():
    with client() as c:
        r = c.get("/stock")
        assert r.status_code == 200 and len(r.json()["items"]) == 12
        before = c.get("/stock/PLAN-001").json()["sims_available"]
        r = c.post("/reserve", json={"plan": "PLAN-001", "qty": 3})
        assert r.status_code == 200 and r.json()["remaining"] == before - 3
        assert c.post("/reserve", json={"plan": "NOPE", "qty": 1}).status_code == 404
        assert c.post("/reserve", json={"plan": "PLAN-002", "qty": 0}).status_code == 422


def test_insufficient_stock():
    with client() as c:
        inventory.STOCK["PLAN-003"] = 1
        assert c.post("/reserve", json={"plan": "PLAN-003", "qty": 2}).status_code == 409
        inventory.STOCK["PLAN-003"] = 100000


def test_fault_switch_adds_latency_and_errors():
    with client() as c:
        assert c.post("/admin/fault", json={"latency_ms": 150, "error_rate": 0}).status_code == 200
        t0 = time.perf_counter()
        assert c.get("/stock").status_code == 200
        assert time.perf_counter() - t0 >= 0.15
        c.post("/admin/fault", json={"latency_ms": 0, "error_rate": 1.0})
        assert c.get("/stock").status_code == 500
        c.post("/admin/fault", json={"latency_ms": 0, "error_rate": 0})
        assert c.get("/stock").status_code == 200


def test_health_and_metrics():
    with client() as c:
        assert c.get("/healthz").json()["status"] == "ok"
        c.get("/stock")
        body = c.get("/metrics").text
        assert 'http_requests_total{method="GET",route="/stock",status="200"}' in body
        assert "http_request_duration_seconds_bucket" in body

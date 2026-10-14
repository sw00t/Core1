# Developing the sample services

All five services (gateway, orders, inventory, loadgen, alert-sink) are one Python package,
`services/app/core1app`, built into one image per service with `CORE1_SERVICE` baked in.

```
cd services/app
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
python -m pytest -q
```

Run the chain locally without Kubernetes (orders uses an in-memory store with `DB_DSN=memory://`):

```
CORE1_SERVICE=inventory PORT=8083 python -m core1app &
CORE1_SERVICE=orders PORT=8082 DB_DSN=memory:// INVENTORY_URL=http://127.0.0.1:8083 python -m core1app &
CORE1_SERVICE=gateway PORT=8081 ORDERS_URL=http://127.0.0.1:8082 INVENTORY_URL=http://127.0.0.1:8083 python -m core1app &
curl -s -X POST localhost:8081/api/orders -H 'content-type: application/json' -d '{"plan":"PLAN-005","qty":1,"channel":"retail"}'
```

Conventions:
- `/healthz` readiness (503 until the service can serve), `/livez` liveness, `/metrics` Prometheus.
- Every request logs one JSON line with `route`, `status`, `duration_ms`, `trace_id`.
- W3C `traceparent` is accepted and propagated to upstream calls, so one `trace_id` spans gateway,
  orders and inventory logs.
- Timeouts become 504, transport failures and upstream 5xx become 502, upstream 4xx pass through.
- Configuration is environment variables only; in the cluster they come from the config repo's ConfigMaps.

Rebuild and reload images after a change: `make images` then `make deploy` (a rollout restart is needed
if the tag did not change: `kubectl -n core1-app rollout restart deploy`).

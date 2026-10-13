"""Default Alertmanager webhook receiver. Logs every notification (so it lands in Loki) and keeps the
last 200 in memory for the verify suite and for humans: GET /alerts."""
import collections
import time

from fastapi import Request

from .common import create_app, log

app = create_app("alert-sink")
received = collections.deque(maxlen=200)


@app.post("/webhook")
async def webhook(request: Request):
    payload = await request.json()
    alerts = payload.get("alerts", [])
    entry = {
        "received_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "status": payload.get("status"),
        "group_labels": payload.get("groupLabels", {}),
        "alertnames": sorted({a.get("labels", {}).get("alertname", "?") for a in alerts}),
        "firing": [a for a in alerts if a.get("status") == "firing"],
        "resolved": [a for a in alerts if a.get("status") == "resolved"],
        "payload": payload,
    }
    received.appendleft(entry)
    log.info("alert notification", extra={
        "status": entry["status"], "alertnames": entry["alertnames"],
        "firing": len(entry["firing"]), "resolved": len(entry["resolved"]),
        "group": entry["group_labels"],
    })
    return {"ok": True}


@app.get("/alerts")
async def alerts(limit: int = 50):
    return [dict(e, payload=None) for e in list(received)[:limit]]


@app.get("/alerts/full")
async def alerts_full(limit: int = 20):
    return list(received)[:limit]


@app.delete("/alerts")
async def clear():
    received.clear()
    return {"ok": True}

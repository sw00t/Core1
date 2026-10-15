#!/usr/bin/env python3
"""Generate observability/dashboards/core1-services.yaml (Grafana dashboard as a ConfigMap). Run after editing."""
import json, os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROM = {"type": "prometheus", "uid": "prometheus"}
LOKI = {"type": "loki", "uid": "loki"}
NS = 'namespace="core1-app"'


def ts(title, targets, unit, x, y, w=12, h=8, threshold=None, desc=None):
    p = {"type": "timeseries", "title": title, "gridPos": {"x": x, "y": y, "w": w, "h": h}, "datasource": PROM,
         "fieldConfig": {"defaults": {"unit": unit, "custom": {"lineWidth": 1, "fillOpacity": 10}}, "overrides": []},
         "options": {"legend": {"displayMode": "list", "placement": "bottom"}, "tooltip": {"mode": "multi"}},
         "targets": [{"refId": chr(65 + i), "expr": e, "legendFormat": l} for i, (e, l) in enumerate(targets)]}
    if threshold is not None:
        p["fieldConfig"]["defaults"]["thresholds"] = {"mode": "absolute", "steps": [{"color": "green", "value": None}, {"color": "red", "value": threshold}]}
        p["fieldConfig"]["defaults"]["custom"]["thresholdsStyle"] = {"mode": "line"}
    if desc:
        p["description"] = desc
    return p


def stat(title, expr, unit, x, y, w=6, h=5, red_above=None, decimals=0, desc=None):
    steps = [{"color": "green", "value": None}]
    if red_above is not None:
        steps.append({"color": "red", "value": red_above})
    p = {"type": "stat", "title": title, "gridPos": {"x": x, "y": y, "w": w, "h": h}, "datasource": PROM,
         "fieldConfig": {"defaults": {"unit": unit, "decimals": decimals, "thresholds": {"mode": "absolute", "steps": steps}}, "overrides": []},
         "options": {"reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False}, "colorMode": "value", "graphMode": "area", "textMode": "value"},
         "targets": [{"refId": "A", "expr": expr}]}
    if desc:
        p["description"] = desc
    return p


def logs(title, expr, x, y, w=24, h=8):
    return {"type": "logs", "title": title, "gridPos": {"x": x, "y": y, "w": w, "h": h}, "datasource": LOKI,
            "options": {"showTime": True, "wrapLogMessage": True, "sortOrder": "Descending"}, "targets": [{"refId": "A", "expr": expr}]}


def row(title, y):
    return {"type": "row", "title": title, "gridPos": {"x": 0, "y": y, "w": 24, "h": 1}, "collapsed": False, "panels": []}


panels = [
    row("Activations (the business metric the NOC watches)", 0),
    stat("Activations per minute", "cascadia:activations_per_min", "short", 0, 1, desc="SIM activation orders completing at the gateway, per minute, over a 2m window."),
    stat("Failed activations per minute", "cascadia:failed_activations_per_min", "short", 6, 1, red_above=1, decimals=1, desc="Activation orders that returned 5xx at the gateway. Severity is derived from the ratio of these two."),
    stat("Failure ratio", "cascadia:failed_activations_per_min / cascadia:activations_per_min", "percentunit", 12, 1, red_above=0.05, decimals=1),
    stat("Pods not ready", f'sum(kube_pod_status_ready{{{NS}, condition="false"}}) or vector(0)', "short", 18, 1, red_above=1),
    ts("Activations vs failures per minute", [("cascadia:activations_per_min", "activations"), ("cascadia:failed_activations_per_min", "failed")], "short", 0, 6, w=24, h=8, threshold=None),
    row("Activation path: gateway, orders, inventory", 14),
    ts("Request rate by service", [(f"sum by (service) (rate(http_requests_total{{{NS}}}[1m]))", "{{service}}")], "reqps", 0, 15),
    ts("5xx ratio by service", [(f"sum by (service) (rate(http_requests_total{{{NS}, status=~\"5..\"}}[1m])) / sum by (service) (rate(http_requests_total{{{NS}}}[1m]))", "{{service}}")], "percentunit", 12, 15, threshold=0.05),
    ts("p95 latency by service", [(f"histogram_quantile(0.95, sum by (service, le) (rate(http_request_duration_seconds_bucket{{{NS}}}[1m])))", "{{service}}")], "s", 0, 23, threshold=0.5),
    ts("Upstream call outcomes", [(f"sum by (service, upstream, outcome) (rate(upstream_requests_total{{{NS}}}[1m]))", "{{service}} -> {{upstream}} {{outcome}}")], "reqps", 12, 23),
    row("Order store (Postgres) and workloads", 31),
    ts("Orders DB pool: connections in use vs max per pod", [(f"sum by (pod) (db_pool_connections_in_use{{{NS}}})", "{{pod}} in use"), (f"max(db_pool_max_connections{{{NS}}})", "max per pod")], "short", 0, 32),
    ts("DB pool acquire timeouts per second", [(f"sum by (pod) (rate(db_pool_acquire_timeouts_total{{{NS}}}[1m]))", "{{pod}}")], "short", 12, 32),
    ts("Container restarts (5m)", [(f"sum by (pod) (increase(kube_pod_container_status_restarts_total{{{NS}}}[5m]))", "{{pod}}")], "short", 0, 40),
    ts("Deployment replicas: available vs desired", [(f"kube_deployment_status_replicas_available{{{NS}}}", "{{deployment}} available"), (f"kube_deployment_spec_replicas{{{NS}}}", "{{deployment}} desired")], "short", 12, 40),
    row("Changes and errors", 48),
    logs("Deploy events (every change that reached the cluster)", '{job="deploy-events"}', 0, 49, h=7),
    logs("Service errors (5xx and upstream failures)", '{namespace="core1-app"} |= "\\"level\\": \\"error\\""', 0, 56, h=10),
]
for i, p in enumerate(panels):
    p["id"] = i + 1
dash = {"uid": "core1-services", "title": "Cascadia Mobile / Activation platform", "tags": ["core1", "cascadia"], "timezone": "browser",
        "schemaVersion": 39, "version": 2, "refresh": "15s", "time": {"from": "now-30m", "to": "now"}, "editable": True, "panels": panels,
        "templating": {"list": []},
        "annotations": {"list": [{"name": "Deploys", "datasource": LOKI, "enable": True, "expr": '{job="deploy-events"}', "iconColor": "blue", "titleFormat": "deploy"}]}}
js = json.dumps(dash, indent=2)
out = "# Provisioned through the Grafana sidecar (label grafana_dashboard=1). Generated by scripts/gen_dashboard.py; edit that, not this.\n"
out += "apiVersion: v1\nkind: ConfigMap\nmetadata:\n  name: core1-dashboard-services\n  labels:\n    grafana_dashboard: \"1\"\n    app.kubernetes.io/part-of: core1\ndata:\n  core1-services.json: |\n"
out += "".join("    " + line + "\n" for line in js.splitlines())
open(os.path.join(ROOT, "observability", "dashboards", "core1-services.yaml"), "w").write(out)
print("wrote observability/dashboards/core1-services.yaml with", len(panels), "panels")

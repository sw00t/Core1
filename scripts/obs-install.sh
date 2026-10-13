#!/usr/bin/env bash
# Observability: kube-prometheus-stack via Helm (Prometheus, Alertmanager, Grafana, kube-state-metrics,
# node-exporter, operator), then Loki and Alloy as plain manifests, then lab alert rules, dashboard,
# ServiceMonitor and NodePort services. Idempotent.
. "$(dirname "$0")/lib.sh"
require_cluster
obs="$ROOT/observability"

log "rendering kube-prometheus-stack values"
"$PYTHON" - "$obs/kube-prometheus-stack-values.yaml" "$WORK/kps-values.rendered.yaml" <<'PY'
import os, sys
src, dst = sys.argv[1], sys.argv[2]
s = open(src).read()
s = s.replace("__ALERT_WEBHOOK_URL__", os.environ["ALERT_WEBHOOK_URL"])
s = s.replace("__GRAFANA_ADMIN_PASSWORD__", os.environ["GRAFANA_ADMIN_PASSWORD"])
s = s.replace("__NS_OBS__", os.environ["NS_OBS"])
open(dst, "w").write(s)
PY

log "installing kube-prometheus-stack $KPS_CHART_VERSION (this pulls several images; first time takes a few minutes)"
if ! "$HELM" upgrade --install kps "$KPS_CHART_OCI" --version "$KPS_CHART_VERSION" \
      -n "$NS_OBS" --create-namespace -f "$WORK/kps-values.rendered.yaml" --timeout 15m >"$ROOT/logs/helm-kps.log" 2>&1; then
  warn "OCI install failed (see logs/helm-kps.log); trying the classic chart repository"
  "$HELM" upgrade --install kps kube-prometheus-stack --repo "$KPS_CHART_REPO" --version "$KPS_CHART_VERSION" \
      -n "$NS_OBS" --create-namespace -f "$WORK/kps-values.rendered.yaml" --timeout 15m >>"$ROOT/logs/helm-kps.log" 2>&1 \
      || die "helm install of kube-prometheus-stack failed; see logs/helm-kps.log"
fi

log "applying Loki, Alloy, nodeports"
mkdir -p "$WORK/rendered"
for f in loki/loki.yaml alloy/alloy.yaml; do
  "$PYTHON" - "$obs/$f" "$WORK/rendered/$(basename "$f")" <<'PYR'
import os, sys
s = open(sys.argv[1]).read()
s = s.replace("__LOKI_IMAGE__", os.environ["LOKI_IMAGE"]).replace("__ALLOY_IMAGE__", os.environ["ALLOY_IMAGE"]).replace("core1-observability", os.environ["NS_OBS"])
open(sys.argv[2], "w").write(s)
PYR
done
"$KUBECTL" apply -n "$NS_OBS" -f "$WORK/rendered/loki.yaml" >/dev/null
"$KUBECTL" apply -n "$NS_OBS" -f "$WORK/rendered/alloy.yaml" >/dev/null
"$KUBECTL" apply -n "$NS_OBS" -f "$obs/nodeports.yaml" >/dev/null

log "waiting for the operator, Prometheus, Alertmanager, Grafana, Loki, Alloy"
wait_pods "$NS_OBS" app.kubernetes.io/name=kube-prometheus-stack-prometheus-operator 300 >/dev/null || wait_pods "$NS_OBS" app=kube-prometheus-stack-operator 60 >/dev/null || true
wait_pods "$NS_OBS" app.kubernetes.io/name=prometheus 420 >/dev/null || die "prometheus not ready"
wait_pods "$NS_OBS" app.kubernetes.io/name=alertmanager 300 >/dev/null || die "alertmanager not ready"
wait_pods "$NS_OBS" app.kubernetes.io/name=grafana 420 >/dev/null || die "grafana not ready"
wait_pods "$NS_OBS" app.kubernetes.io/name=loki 300 >/dev/null || die "loki not ready"
wait_pods "$NS_OBS" app.kubernetes.io/name=alloy 300 >/dev/null || die "alloy not ready"

# CRD-dependent objects go last, once the operator has registered the CRDs.
"$KUBECTL" apply -n "$NS_OBS" -f "$obs/rules/" >/dev/null
"$KUBECTL" apply -n "$NS_OBS" -f "$obs/app-servicemonitor.yaml" >/dev/null
"$KUBECTL" apply -n "$NS_OBS" -f "$obs/dashboards/" >/dev/null

wait_http "$PROM_URL/-/ready" 120 >/dev/null || die "prometheus not reachable on $PROM_URL"
wait_http "$ALERTMANAGER_URL/-/ready" 120 >/dev/null || die "alertmanager not reachable on $ALERTMANAGER_URL"
wait_http "$LOKI_URL/ready" 180 >/dev/null || die "loki not reachable on $LOKI_URL"
wait_http "$GRAFANA_URL/api/health" 120 >/dev/null || die "grafana not reachable on $GRAFANA_URL"
log "observability stack ready"

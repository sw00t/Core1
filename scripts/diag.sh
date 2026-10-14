#!/usr/bin/env bash
# Snapshot for remote debugging: cluster objects, failing pods, recent events, alerts, targets, docker.
. "$(dirname "$0")/lib.sh"
ts=$(date +%Y%m%d-%H%M%S); out="$ROOT/logs/diag-$ts"; mkdir -p "$out"
{
  echo "== $(date) host $(host_os)/$(host_arch)"
  docker info --format 'docker: {{.ServerVersion}} cpus={{.NCPU}} mem={{.MemTotal}}' 2>&1
  docker ps -a --format 'table {{.Names}}\t{{.Status}}\t{{.Image}}' 2>&1
  docker stats --no-stream --format 'table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}' 2>&1
} > "$out/docker.txt"
if [ -x "$K3D" ] && cluster_exists && [ -f "$KUBECONFIG" ]; then
  "$KUBECTL" get nodes -o wide > "$out/nodes.txt" 2>&1
  "$KUBECTL" top nodes >> "$out/nodes.txt" 2>&1 || true
  "$KUBECTL" get all -A -o wide > "$out/all.txt" 2>&1
  "$KUBECTL" top pods -A >> "$out/all.txt" 2>&1 || true
  "$KUBECTL" get events -A --sort-by=.lastTimestamp 2>&1 | tail -150 > "$out/events.txt"
  "$KUBECTL" get pods -A --no-headers 2>/dev/null | awk '{ split($2, r, "/"); if (($4 != "Running" && $4 != "Completed") || r[1] != r[2] || $5+0 > 0) print $1" "$2 }' | while read -r ns pod; do
    [ -n "$pod" ] || continue
    { "$KUBECTL" -n "$ns" describe pod "$pod" || true; echo "---- logs (tail 80)"; "$KUBECTL" -n "$ns" logs "$pod" --all-containers --tail=80 || true; echo "---- previous"; "$KUBECTL" -n "$ns" logs "$pod" --all-containers --tail=40 --previous || true; } > "$out/pod-$ns-$pod.txt" 2>&1 || true
  done
  "$HELM" list -A > "$out/helm.txt" 2>&1 || true
  "$KUBECTL" -n "$NS_OBS" get prometheusrules,servicemonitors,prometheus,alertmanager -o wide > "$out/operator-objects.txt" 2>&1 || true
  curl -fsS -m 5 "$PROM_URL/api/v1/targets" > "$out/prom-targets.json" 2>&1 || echo "prometheus unreachable" > "$out/prom-targets.json"
  curl -fsS -m 5 "$PROM_URL/api/v1/rules" > "$out/prom-rules.json" 2>&1 || true
  curl -fsS -m 5 "$ALERTMANAGER_URL/api/v2/alerts" > "$out/am-alerts.json" 2>&1 || echo "alertmanager unreachable" > "$out/am-alerts.json"
  curl -fsS -m 5 "$ALERTMANAGER_URL/api/v2/status" > "$out/am-status.json" 2>&1 || true
  curl -fsS -m 5 "$ALERT_SINK_URL/alerts" > "$out/alert-sink.json" 2>&1 || true
  curl -fsS -m 5 "$LOKI_URL/ready" > "$out/loki-ready.txt" 2>&1 || true
  curl -fsS -m 10 -G "$LOKI_URL/loki/api/v1/series" --data-urlencode 'match[]={namespace=~".+"}' > "$out/loki-series.json" 2>&1 || true
  for s in gateway orders inventory; do "$KUBECTL" -n "$NS_APP" logs -l app.kubernetes.io/name=$s --tail=40 --all-containers > "$out/logs-$s.txt" 2>&1 || true; done
  "$KUBECTL" -n "$NS_SYS" logs -l app.kubernetes.io/name=loadgen --tail=30 > "$out/logs-loadgen.txt" 2>&1 || true
  "$KUBECTL" -n "$NS_OBS" logs -l app.kubernetes.io/name=alloy --tail=40 > "$out/logs-alloy.txt" 2>&1 || true
  "$KUBECTL" -n "$NS_OBS" logs -l app.kubernetes.io/name=loki --tail=40 > "$out/logs-loki.txt" 2>&1 || true
  ( cd "$CONFIG_REPO" 2>/dev/null && git log --oneline -10 && git status --short ) > "$out/config-repo.txt" 2>&1 || true
fi
"$PYTHON" "$ROOT/scripts/disk_check.py" --json > "$out/disk.json" 2>&1 || true
log "diagnostics written to $out"
ls "$out"

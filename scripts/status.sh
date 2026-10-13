#!/usr/bin/env bash
# One-screen summary.
. "$(dirname "$0")/lib.sh"
if ! [ -x "$K3D" ] || ! cluster_exists; then log "cluster '$CLUSTER_NAME' is not running"; exit 0; fi
echo "== nodes"; "$KUBECTL" get nodes -o wide --no-headers 2>/dev/null | awk '{print "  "$1, $2, $5}'
for ns in "$NS_APP" "$NS_SYS" "$NS_OBS"; do
  echo "== $ns"
  "$KUBECTL" -n "$ns" get pods --no-headers 2>/dev/null | awk '{printf "  %-52s %-10s %-20s %s\n", $1, $2, $3, $4}'
done
echo "== config repo"
if [ -d "$CONFIG_REPO/.git" ]; then (cd "$CONFIG_REPO" && git log --oneline -5 | sed 's/^/  /'); else echo "  not initialized"; fi
echo "== lab alerts (Alertmanager)"
curl -fsS -m 5 "$ALERTMANAGER_URL/api/v2/alerts?active=true&filter=lab%3D%22core1%22" 2>/dev/null \
  | "$PYTHON" -c 'import sys,json
a=json.load(sys.stdin)
print("  none" if not a else "\n".join("  %-32s %-10s %s"%(x["labels"].get("alertname"),x["labels"].get("severity",""),x["labels"].get("service") or x["labels"].get("pod","")) for x in a))' 2>/dev/null || echo "  alertmanager not reachable"
echo "== endpoints"; grep -E '^CORE1_(PROMETHEUS|ALERTMANAGER|LOKI|GRAFANA|GATEWAY|ALERT_SINK)_URL=' "$WORK/endpoints.env" 2>/dev/null | sed -e 's/^CORE1_//' -e 's/_URL=/ /' -e 's/^/  /' || true
"$PYTHON" "$ROOT/scripts/disk_check.py" --report || true

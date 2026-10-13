#!/usr/bin/env bash
# Block until app deployments are fully available and no lab alert is active.
. "$(dirname "$0")/lib.sh"
require_cluster
timeout="${1:-480}"
start=$(date +%s)
log "waiting for a green system (timeout ${timeout}s)"
while :; do
  ok=1
  for d in $("$KUBECTL" -n "$NS_APP" get deploy -o name 2>/dev/null); do
    "$KUBECTL" -n "$NS_APP" rollout status "$d" --timeout=5s >/dev/null 2>&1 || ok=0
  done
  if [ "$ok" = 1 ]; then
    active=$(curl -fsS -m 5 "$ALERTMANAGER_URL/api/v2/alerts?active=true&silenced=false&inhibited=false&filter=lab%3D%22core1%22" 2>/dev/null \
      | "$PYTHON" -c 'import sys,json; a=json.load(sys.stdin); print(len(a)); [sys.stderr.write("  firing: %s %s\n"%(x["labels"].get("alertname"),x["labels"].get("service",x["labels"].get("pod","")))) for x in a]' 2>/dev/null || echo "?")
    if [ "$active" = "0" ]; then
      # Also require Prometheus to be scraping the app and seeing traffic, so verify can run right away.
      scraped=$(curl -fsS -m 5 "$PROM_URL/api/v1/targets?state=active" 2>/dev/null | "$PYTHON" -c '
import sys, json
want = {"gateway": 2, "orders": 2, "inventory": 2, "loadgen": 1, "alert-sink": 1}
up = {}
for t in json.load(sys.stdin)["data"]["activeTargets"]:
    l = t.get("labels", {})
    if l.get("service") in want and t.get("health") == "up":
        up[l["service"]] = up.get(l["service"], 0) + 1
print("yes" if all(up.get(s, 0) >= n for s, n in want.items()) else "no")' 2>/dev/null || echo no)
      traffic=$(curl -fsS -m 5 -G "$PROM_URL/api/v1/query" --data-urlencode 'query=sum(rate(http_requests_total{service="gateway"}[1m]))' 2>/dev/null | "$PYTHON" -c '
import sys, json
r = json.load(sys.stdin)["data"]["result"]
print("yes" if r and float(r[0]["value"][1]) > 1 else "no")' 2>/dev/null || echo no)
      if [ "$scraped" = yes ] && [ "$traffic" = yes ]; then log "green: deployments available, no lab alerts, app targets scraped, traffic flowing"; exit 0; fi
      log "deployments ready; waiting for Prometheus targets (scraped=$scraped traffic=$traffic)"
    fi
  fi
  now=$(date +%s)
  if [ $((now - start)) -ge "$timeout" ]; then
    warn "not green after ${timeout}s"
    "$KUBECTL" -n "$NS_APP" get deploy,pods || true
    exit 1
  fi
  sleep 10
done

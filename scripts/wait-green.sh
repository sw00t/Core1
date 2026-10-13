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
    if [ "$active" = "0" ]; then log "green: deployments available, no lab alerts active"; exit 0; fi
  fi
  now=$(date +%s)
  if [ $((now - start)) -ge "$timeout" ]; then
    warn "not green after ${timeout}s"
    "$KUBECTL" -n "$NS_APP" get deploy,pods || true
    exit 1
  fi
  sleep 10
done

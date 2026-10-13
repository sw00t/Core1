#!/usr/bin/env bash
# Preflight: does this machine have what the lab needs? Exit 1 on hard failures.
. "$(dirname "$0")/lib.sh"
fail=0
ok()   { printf '  ok    %s\n' "$*"; }
bad()  { printf '  FAIL  %s\n' "$*"; fail=1; }
note() { printf '  note  %s\n' "$*"; }

log "doctor: $(host_os)/$(host_arch)"

for t in docker make bash git curl tar; do
  if command -v "$t" >/dev/null 2>&1; then ok "$t: $(command -v "$t")"; else bad "$t not found"; fi
done
if command -v "$PYTHON" >/dev/null 2>&1; then
  pv=$("$PYTHON" -c 'import sys; print("%d.%d" % sys.version_info[:2])')
  if "$PYTHON" -c 'import sys; sys.exit(0 if sys.version_info >= (3,9) else 1)'; then ok "python3 $pv"; else bad "python3 >= 3.9 required, found $pv"; fi
else bad "python3 not found (stdlib only is enough)"; fi

if docker info >/dev/null 2>&1; then
  mem=$(docker info --format '{{.MemTotal}}' 2>/dev/null || echo 0)
  cpus=$(docker info --format '{{.NCPU}}' 2>/dev/null || echo 0)
  memgb=$(( mem / 1024 / 1024 / 1024 ))
  ok "docker engine reachable: ${cpus} cpus, ${memgb} GB memory, $(docker info --format '{{.Architecture}}' 2>/dev/null)"
  [ "$memgb" -ge 6 ] || bad "docker has ${memgb} GB memory; the lab needs at least 6 GB (8 recommended)"
  [ "$cpus" -ge 4 ] || note "docker has ${cpus} cpus; 4+ recommended"
else
  bad "docker engine not reachable (is Docker Desktop running?)"
fi

for p in "$API_PORT" "$GATEWAY_PORT" "$ALERT_SINK_PORT" "$PROM_PORT" "$ALERTMANAGER_PORT" "$LOKI_PORT" "$GRAFANA_PORT"; do
  if "$PYTHON" - "$p" <<'PY'
import socket, sys
s = socket.socket(); s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
try:
    s.bind(("127.0.0.1", int(sys.argv[1]))); s.close(); sys.exit(0)
except OSError:
    sys.exit(1)
PY
  then ok "port $p free"; else
    if cluster_exists 2>/dev/null; then note "port $p in use (cluster $CLUSTER_NAME exists, so expected)"; else bad "port $p already in use; change it in .env"; fi
  fi
done

for t in k3d kubectl helm; do
  if [ -x "$BIN/$t" ]; then ok "$t $(cat "$BIN/.$t.version" 2>/dev/null)"; else note "$t not bootstrapped yet (make bootstrap)"; fi
done

"$PYTHON" "$ROOT/scripts/disk_check.py" --report || fail=1

if [ "$fail" -ne 0 ]; then die "doctor found problems"; fi
log "doctor: all good"

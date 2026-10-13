#!/usr/bin/env bash
# Unattended runner. Start it once in a terminal on the host:
#
#   ./scripts/runner.sh
#
# It then executes make targets that are queued as files in .runner/inbox/, one at a time,
# and writes logs to .runner/log/. Only the targets in ALLOWED below can be queued.
# Stop it with Ctrl-C or by creating .runner/stop. On macOS it runs under caffeinate -i so the
# machine does not idle-sleep while the runner is alive (pass --no-caffeinate to skip that).
#
# Queue protocol (what a client writes):
#   .runner/inbox/<id>.cmd   one line: the make target
# What the runner writes:
#   .runner/log/<id>.log     combined stdout/stderr of `make <target>`
#   .runner/done/<id>.rc     exit code, written when the run ends
#   .runner/heartbeat        unix time, touched every loop
#   .runner/state            "idle" or "running <id> <target>"
. "$(dirname "$0")/lib.sh"

ALLOWED='^(doctor|bootstrap|up|down|reset|status|verify|verify-quick|disk|endpoints|images|cluster|obs|secrets|config-repo|deploy|loadgen|agent-kubeconfig|wait-green|scenario-[1-5]|diag|test)$'
NO_DISK_GUARD='^(down|disk|status|diag|doctor|endpoints)$'
R="$ROOT/.runner"
mkdir -p "$R/inbox" "$R/log" "$R/done"

if [ "${1:-}" != "--no-caffeinate" ] && [ "$(host_os)" = "darwin" ] && command -v caffeinate >/dev/null 2>&1; then
  exec caffeinate -i "$0" --no-caffeinate
fi

rm -f "$R/stop"
echo $$ > "$R/pid"
log "runner started (pid $$). Queue dir: $R/inbox. Stop with Ctrl-C or: touch $R/stop"
log "allowed targets: $(printf '%s' "$ALLOWED" | tr -d '^$()' | tr '|' ' ')"
trap 'echo "stopped" > "$R/state"; rm -f "$R/pid"; log "runner stopped"; exit 0' INT TERM

while :; do
  date +%s > "$R/heartbeat"
  if [ -f "$R/stop" ]; then rm -f "$R/stop"; echo "stopped" > "$R/state"; rm -f "$R/pid"; log "stop file seen, exiting"; exit 0; fi
  next=$(ls -1 "$R/inbox" 2>/dev/null | grep '\.cmd$' | sort | head -1 || true)
  if [ -z "$next" ]; then echo "idle" > "$R/state"; sleep 3; continue; fi
  id="${next%.cmd}"
  target=$(head -1 "$R/inbox/$next" | tr -d '[:space:]')
  rm -f "$R/inbox/$next"
  if ! printf '%s' "$target" | grep -Eq "$ALLOWED"; then
    log "refused '$target' (not in allowlist)"; echo "refused: $target" > "$R/log/$id.log"; echo 126 > "$R/done/$id.rc"; continue
  fi
  if ! printf '%s' "$target" | grep -Eq "$NO_DISK_GUARD"; then
    if ! "$PYTHON" "$ROOT/scripts/disk_check.py" --enforce > "$R/log/$id.log" 2>&1; then
      log "refused '$target': disk guard"; echo 125 > "$R/done/$id.rc"; continue
    fi
  fi
  echo "running $id $target" > "$R/state"
  log "run $id: make $target"
  start=$(date +%s)
  ( cd "$ROOT" && make "$target" ) >> "$R/log/$id.log" 2>&1 && rc=0 || rc=$?
  echo "$rc" > "$R/done/$id.rc"
  log "done $id: make $target rc=$rc in $(( $(date +%s) - start ))s"
done

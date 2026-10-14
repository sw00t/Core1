#!/usr/bin/env bash
# Known-good baseline: config repo back to the 'baseline' tag on main, runtime faults cleared,
# baseline deployed, then wait for green.
. "$(dirname "$0")/lib.sh"
require_cluster
[ -d "$CONFIG_REPO/.git" ] || die "config repo not initialized; run: make config-repo"
log "resetting config repo to baseline"
( cd "$CONFIG_REPO" && git checkout -q main && git reset -q --hard baseline && git clean -qfd && git branch --list 'agent/*' | xargs -r git branch -q -D )
"$PYTHON" "$ROOT/scripts/scenario.py" push-main --force
# remote agent/* branches are left alone: the agent repo removes its own branches when an incident closes
"$PYTHON" "$ROOT/scripts/scenario.py" clear-runtime-faults
log "deploying baseline"
"$ROOT/scripts/deploy.sh" --wait
"$ROOT/scripts/wait-green.sh" 600

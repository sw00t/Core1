#!/usr/bin/env bash
# Create the config repo from the template with a seeded, plausible history. Tags the result 'baseline'.
# Idempotent: if the repo exists with a baseline tag, it is left alone (use make reset to restore it).
. "$(dirname "$0")/lib.sh"
if [ -d "$CONFIG_REPO/.git" ] && (cd "$CONFIG_REPO" && git rev-parse -q --verify baseline >/dev/null 2>&1); then
  log "config repo already initialized at $CONFIG_REPO"; exit 0
fi
rm -rf "$CONFIG_REPO"; mkdir -p "$(dirname "$CONFIG_REPO")"
cp -R "$ROOT/config-repo-template" "$CONFIG_REPO"
chmod +x "$CONFIG_REPO/deploy.sh"
# file modes vary across sync tools and sandboxes; git should not treat a mode flip as a change here
( cd "$CONFIG_REPO" && git init -q && git config core.fileMode false )
"$PYTHON" "$ROOT/scripts/seed_history.py" "$CONFIG_REPO" "$ROOT/config-repo-seed/history.json"
log "config repo initialized at $CONFIG_REPO"
(cd "$CONFIG_REPO" && git log --oneline)

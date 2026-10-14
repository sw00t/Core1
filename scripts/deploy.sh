#!/usr/bin/env bash
# Deploy the config repo's HEAD. Thin wrapper that hands the config repo's own deploy.sh the
# platform details it needs (kubectl, kubeconfig, Loki push URL).
. "$(dirname "$0")/lib.sh"
require_cluster
[ -d "$CONFIG_REPO/.git" ] || die "config repo not initialized; run: make config-repo"
export KUBECTL KUBECONFIG
export LOKI_PUSH_URL="$LOKI_URL/loki/api/v1/push"
export DEPLOY_NAMESPACE="$NS_APP"
if ( cd "$CONFIG_REPO" && git remote get-url origin >/dev/null 2>&1 ); then
  log "pulling origin/main (merged PRs) before deploying"
  ( cd "$CONFIG_REPO" && git checkout -q main && git pull -q --ff-only origin main ) || warn "pull failed; deploying local HEAD"
fi
exec "$CONFIG_REPO/deploy.sh" "$@"

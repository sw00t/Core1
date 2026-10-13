#!/usr/bin/env bash
# Deploy the config repo's HEAD. Thin wrapper that hands the config repo's own deploy.sh the
# platform details it needs (kubectl, kubeconfig, Loki push URL).
. "$(dirname "$0")/lib.sh"
require_cluster
[ -d "$CONFIG_REPO/.git" ] || die "config repo not initialized; run: make config-repo"
export KUBECTL KUBECONFIG
export LOKI_PUSH_URL="$LOKI_URL/loki/api/v1/push"
export DEPLOY_NAMESPACE="$NS_APP"
exec "$CONFIG_REPO/deploy.sh" "$@"

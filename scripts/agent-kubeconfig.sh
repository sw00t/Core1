#!/usr/bin/env bash
# Read-only identity for the agent: a ServiceAccount bound to a ClusterRole that can get/list/watch
# workloads, pods, logs, events and config, but not secrets, and cannot write anything.
# Produces .kube/agent-readonly.yaml with a 30-day token. Re-run to refresh.
. "$(dirname "$0")/lib.sh"
require_cluster
"$KUBECTL" apply -f "$ROOT/rbac/agent-readonly.yaml" >/dev/null
token=$("$KUBECTL" -n "$NS_SYS" create token agent-readonly --duration=720h)
ca=$("$KUBECTL" config view --raw --minify -o jsonpath='{.clusters[0].cluster.certificate-authority-data}')
server=$("$KUBECTL" config view --raw --minify -o jsonpath='{.clusters[0].cluster.server}')
out="$KUBE_DIR/agent-readonly.yaml"
cat > "$out" <<Y
apiVersion: v1
kind: Config
clusters:
- name: core1
  cluster:
    server: $server
    certificate-authority-data: $ca
users:
- name: agent-readonly
  user:
    token: $token
contexts:
- name: core1-agent-readonly
  context:
    cluster: core1
    user: agent-readonly
    namespace: $NS_APP
current-context: core1-agent-readonly
Y
chmod 600 "$out"
log "agent read-only kubeconfig: $out"
KUBECONFIG="$out" "$KUBECTL" auth can-i get pods -n "$NS_APP" >/dev/null || die "read-only identity cannot read pods"
if KUBECONFIG="$out" "$KUBECTL" auth can-i get secrets -n "$NS_APP" >/dev/null 2>&1; then die "read-only identity can read secrets; RBAC is wrong"; fi
log "read-only identity verified (pods yes, secrets no)"

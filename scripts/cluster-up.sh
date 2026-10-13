#!/usr/bin/env bash
# Create the k3d cluster with host port mappings. Idempotent: exits early if it exists.
. "$(dirname "$0")/lib.sh"
[ -x "$K3D" ] || die "run make bootstrap first"
docker info >/dev/null 2>&1 || die "docker engine not reachable"

if cluster_exists; then
  log "cluster '$CLUSTER_NAME' already exists"
  "$K3D" cluster start "$CLUSTER_NAME" >/dev/null 2>&1 || true
else
  log "creating k3d cluster '$CLUSTER_NAME' (k3s $K3S_IMAGE, agents=$K3D_AGENTS)"
  # Host ports are bound to loopback only. NodePorts are fixed in the manifests (observability/nodeports.yaml,
  # config repo services) so the mapping below is the single place that ties host ports to them.
  "$K3D" cluster create "$CLUSTER_NAME" \
    --image "$K3S_IMAGE" \
    --servers 1 --agents "$K3D_AGENTS" \
    --api-port "127.0.0.1:$API_PORT" \
    -p "127.0.0.1:$GATEWAY_PORT:30080@server:0" \
    -p "127.0.0.1:$ALERT_SINK_PORT:30081@server:0" \
    -p "127.0.0.1:$PROM_PORT:30090@server:0" \
    -p "127.0.0.1:$ALERTMANAGER_PORT:30093@server:0" \
    -p "127.0.0.1:$LOKI_PORT:30100@server:0" \
    -p "127.0.0.1:$GRAFANA_PORT:30030@server:0" \
    --k3s-arg "--disable=traefik@server:0" \
    --k3s-arg "--disable=servicelb@server:0" \
    --kubeconfig-update-default=false \
    --kubeconfig-switch-context=false \
    --wait --timeout 240s
fi

"$K3D" kubeconfig get "$CLUSTER_NAME" | sed "s#https://0.0.0.0:#https://127.0.0.1:#" > "$KUBECONFIG"
chmod 600 "$KUBECONFIG"
log "kubeconfig written to $KUBECONFIG"

log "waiting for the node and core components"
"$KUBECTL" wait --for=condition=Ready node --all --timeout=180s >/dev/null
wait_pods kube-system k8s-app=kube-dns 180 >/dev/null || die "coredns not ready"
for ns in "$NS_APP" "$NS_OBS" "$NS_SYS"; do
  "$KUBECTL" create namespace "$ns" --dry-run=client -o yaml | "$KUBECTL" apply -f - >/dev/null
done
"$KUBECTL" get nodes

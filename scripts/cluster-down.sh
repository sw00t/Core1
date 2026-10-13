#!/usr/bin/env bash
# Delete the cluster (containers and their volumes). Built images and .bin stay.
. "$(dirname "$0")/lib.sh"
if [ -x "$K3D" ] && cluster_exists; then
  log "deleting cluster '$CLUSTER_NAME'"
  "$K3D" cluster delete "$CLUSTER_NAME"
else
  log "cluster '$CLUSTER_NAME' not present"
fi
rm -f "$KUBECONFIG" "$KUBE_DIR/agent-readonly.yaml" "$WORK/endpoints.env" "$WORK/endpoints.json"
log "down. Config repo kept at $CONFIG_REPO (make reset to restore baseline later)"

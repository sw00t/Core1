#!/usr/bin/env bash
# Build the sample service images from one Dockerfile and import them into the cluster.
# All images share layers; only the CORE1_SERVICE env differs.
. "$(dirname "$0")/lib.sh"
require_cluster
cd "$ROOT/services/app" || exit 1
services="gateway orders inventory loadgen alert-sink"
for s in $services; do
  img="core1.local/$s:$APP_VERSION"
  log "building $img"
  docker build -q --build-arg "BASE_IMAGE=$PYTHON_BASE_IMAGE" --build-arg "SERVICE=$s" -t "$img" . >/dev/null
done
imgs=""
for s in $services; do imgs="$imgs core1.local/$s:$APP_VERSION"; done
log "importing images into cluster '$CLUSTER_NAME'"
# shellcheck disable=SC2086
"$K3D" image import $imgs -c "$CLUSTER_NAME" >/dev/null
log "images ready"

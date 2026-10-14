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
# Same tag, new content: restart whatever already runs these images so the cluster picks them up.
for ns in "$NS_APP" "$NS_SYS"; do
  for d in $("$KUBECTL" -n "$ns" get deploy -o json 2>/dev/null | "$PYTHON" -c 'import sys,json; [print(d["metadata"]["name"]) for d in json.load(sys.stdin)["items"] if any(c["image"].startswith("core1.local/") for c in d["spec"]["template"]["spec"]["containers"])]'); do
    "$KUBECTL" -n "$ns" rollout restart "deploy/$d" >/dev/null && log "restarted $ns/$d"
  done
done

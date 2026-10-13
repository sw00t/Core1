#!/usr/bin/env bash
# Remove built images, downloaded tools and local state. Does not touch other Docker images.
. "$(dirname "$0")/lib.sh"
for img in $(docker images --format '{{.Repository}}:{{.Tag}}' | grep '^core1.local/' || true); do
  docker rmi "$img" >/dev/null 2>&1 && log "removed image $img"
done
rm -rf "$BIN" "$WORK/dl" "$WORK/helm" "$WORK/kps-values.rendered.yaml"
log "clean. Kept: $CONFIG_REPO, logs/, reports/"

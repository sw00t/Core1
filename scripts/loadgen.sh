#!/usr/bin/env bash
# Lab plumbing in core1-system: synthetic load generator and the default alert sink.
. "$(dirname "$0")/lib.sh"
require_cluster
"$PYTHON" - "$ROOT/cluster/lab-system.yaml" <<'PY' | "$KUBECTL" apply -n "$NS_SYS" -f - >/dev/null
import os, sys
s = open(sys.argv[1]).read()
s = s.replace("__APP_VERSION__", os.environ["APP_VERSION"]).replace("__LOAD_RPS__", os.environ["LOAD_RPS"]).replace("__NS_APP__", os.environ["NS_APP"])
sys.stdout.write(s)
PY
wait_pods "$NS_SYS" app.kubernetes.io/name=alert-sink 180 >/dev/null || die "alert-sink not ready"
wait_pods "$NS_SYS" app.kubernetes.io/name=loadgen 180 >/dev/null || die "loadgen not ready"
log "loadgen ($LOAD_RPS rps) and alert-sink running in $NS_SYS"

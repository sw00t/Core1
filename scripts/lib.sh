#!/usr/bin/env bash
# Shared helpers. Source this from every script: . "$(dirname "$0")/lib.sh"
# Works with macOS bash 3.2 and Linux bash 4/5.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export ROOT

# Pinned versions, then optional user overrides from .env
set -a
# shellcheck disable=SC1091
. "$ROOT/versions.env"
if [ -f "$ROOT/.env" ]; then
  # shellcheck disable=SC1091
  . "$ROOT/.env"
fi
set +a

# Defaults (overridable from .env or the environment)
: "${CLUSTER_NAME:=core1}"
: "${API_PORT:=16443}"
: "${GATEWAY_PORT:=18080}"
: "${ALERT_SINK_PORT:=18081}"
: "${PROM_PORT:=19090}"
: "${ALERTMANAGER_PORT:=19093}"
: "${LOKI_PORT:=13100}"
: "${GRAFANA_PORT:=13000}"
: "${K3D_AGENTS:=0}"
: "${DISK_CEILING_GB:=20}"
: "${HOST_FREE_MIN_GB:=6}"
: "${GRAFANA_ADMIN_PASSWORD:=core1-admin}"
: "${ALERT_WEBHOOK_URL:=http://alert-sink.core1-system.svc:8080/webhook}"
: "${LOAD_RPS:=40}"
: "${CONFIG_REPO_DIR:=.work/config-repo}"
export CLUSTER_NAME API_PORT GATEWAY_PORT ALERT_SINK_PORT PROM_PORT ALERTMANAGER_PORT LOKI_PORT GRAFANA_PORT
export K3D_AGENTS DISK_CEILING_GB HOST_FREE_MIN_GB GRAFANA_ADMIN_PASSWORD ALERT_WEBHOOK_URL LOAD_RPS

# Namespaces
NS_APP=core1-app
NS_OBS=core1-observability
NS_SYS=core1-system
export NS_APP NS_OBS NS_SYS

# Paths
BIN="$ROOT/.bin"
WORK="$ROOT/.work"
KUBE_DIR="$ROOT/.kube"
mkdir -p "$BIN" "$WORK" "$KUBE_DIR" "$ROOT/logs" "$ROOT/reports"
case "$CONFIG_REPO_DIR" in
  /*) CONFIG_REPO="$CONFIG_REPO_DIR" ;;
  *)  CONFIG_REPO="$ROOT/$CONFIG_REPO_DIR" ;;
esac
export BIN WORK KUBE_DIR CONFIG_REPO

# Tools: always the pinned copies in .bin, never whatever is on PATH
export PATH="$BIN:$PATH"
K3D="$BIN/k3d"
KUBECTL="$BIN/kubectl"
HELM="$BIN/helm"
export K3D KUBECTL HELM

# Keep kube and helm state inside the repo
export KUBECONFIG="$KUBE_DIR/admin.yaml"
export HELM_CACHE_HOME="$WORK/helm/cache"
export HELM_CONFIG_HOME="$WORK/helm/config"
export HELM_DATA_HOME="$WORK/helm/data"
export HELM_REGISTRY_CONFIG="$WORK/helm/registry.json"
export HELM_REPOSITORY_CACHE="$WORK/helm/repo-cache"
export HELM_REPOSITORY_CONFIG="$WORK/helm/repositories.yaml"
mkdir -p "$WORK/helm"

# Endpoints (host side)
PROM_URL="http://127.0.0.1:$PROM_PORT"
ALERTMANAGER_URL="http://127.0.0.1:$ALERTMANAGER_PORT"
LOKI_URL="http://127.0.0.1:$LOKI_PORT"
GRAFANA_URL="http://127.0.0.1:$GRAFANA_PORT"
GATEWAY_URL="http://127.0.0.1:$GATEWAY_PORT"
ALERT_SINK_URL="http://127.0.0.1:$ALERT_SINK_PORT"
export PROM_URL ALERTMANAGER_URL LOKI_URL GRAFANA_URL GATEWAY_URL ALERT_SINK_URL

PYTHON="${PYTHON:-python3}"
export PYTHON

log()  { printf '%s [core1] %s\n' "$(date '+%H:%M:%S')" "$*"; }
warn() { printf '%s [core1] WARN: %s\n' "$(date '+%H:%M:%S')" "$*" >&2; }
die()  { printf '%s [core1] ERROR: %s\n' "$(date '+%H:%M:%S')" "$*" >&2; exit 1; }

host_os()   { uname -s | tr '[:upper:]' '[:lower:]'; }
host_arch() {
  case "$(uname -m)" in
    x86_64|amd64) echo amd64 ;;
    arm64|aarch64) echo arm64 ;;
    *) die "unsupported CPU architecture: $(uname -m)" ;;
  esac
}

cluster_exists() { "$K3D" cluster list -o json 2>/dev/null | "$PYTHON" -c 'import sys,json; sys.exit(0 if any(c.get("name")=="'"$CLUSTER_NAME"'" for c in json.load(sys.stdin)) else 1)'; }

# wait_pods NAMESPACE LABEL_SELECTOR TIMEOUT_SECONDS
# Waits for at least one pod to exist, then for all matching pods to be Ready.
wait_pods() {
  local ns="$1" sel="$2" timeout="${3:-300}" start now n
  start=$(date +%s)
  while :; do
    n=$("$KUBECTL" -n "$ns" get pods -l "$sel" --no-headers 2>/dev/null | wc -l | tr -d ' ')
    if [ "$n" -gt 0 ]; then
      if "$KUBECTL" -n "$ns" wait --for=condition=Ready pod -l "$sel" --timeout=20s >/dev/null 2>&1; then
        return 0
      fi
    fi
    now=$(date +%s)
    if [ $((now - start)) -ge "$timeout" ]; then
      warn "timed out waiting for pods -n $ns -l $sel"
      "$KUBECTL" -n "$ns" get pods -l "$sel" || true
      return 1
    fi
    sleep 5
  done
}

# wait_http URL TIMEOUT_SECONDS [EXPECTED_SUBSTRING]
wait_http() {
  local url="$1" timeout="${2:-120}" want="${3:-}" start now body
  start=$(date +%s)
  while :; do
    body=$(curl -fsS -m 5 "$url" 2>/dev/null || true)
    if [ -n "$body" ] || curl -fsS -m 5 -o /dev/null "$url" 2>/dev/null; then
      if [ -z "$want" ] || printf '%s' "$body" | grep -q -- "$want"; then
        return 0
      fi
    fi
    now=$(date +%s)
    if [ $((now - start)) -ge "$timeout" ]; then
      warn "timed out waiting for $url"
      return 1
    fi
    sleep 3
  done
}

require_cluster() {
  [ -x "$K3D" ] || die "tools missing; run: make bootstrap"
  cluster_exists || die "cluster '$CLUSTER_NAME' does not exist; run: make up"
  [ -f "$KUBECONFIG" ] || die "kubeconfig missing at $KUBECONFIG; run: make up"
}

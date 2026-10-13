#!/usr/bin/env bash
# Apply overlays/prod to the cluster and record a deploy event.
#
# Environment (set by the platform wrapper; sensible defaults for manual use):
#   KUBECTL           kubectl binary (default: kubectl on PATH)
#   KUBECONFIG        cluster credentials
#   DEPLOY_NAMESPACE  namespace of the workloads (default: core1-app)
#   LOKI_PUSH_URL     optional; when set, a JSON deploy event is pushed to Loki ({job="deploy-events"})
# Flags:
#   --wait            wait for every deployment rollout to complete (default: return after apply)
#   --allow-dirty     deploy a dirty working tree (for local experiments only)
set -euo pipefail
cd "$(dirname "$0")"
KUBECTL="${KUBECTL:-kubectl}"
NS="${DEPLOY_NAMESPACE:-core1-app}"
WAIT=0; ALLOW_DIRTY=0
for a in "$@"; do case "$a" in --wait) WAIT=1;; --allow-dirty) ALLOW_DIRTY=1;; *) echo "unknown flag $a" >&2; exit 2;; esac; done

if [ "$ALLOW_DIRTY" = 0 ] && ! git diff --quiet HEAD --; then
  echo "deploy.sh: working tree has uncommitted changes; commit first (or --allow-dirty)" >&2; exit 1
fi

sha=$(git rev-parse HEAD); short=$(git rev-parse --short HEAD)
subject=$(git log -1 --pretty=%s); author=$(git log -1 --pretty='%an <%ae>'); committed=$(git log -1 --pretty=%cI)
files=$(git diff-tree --no-commit-id --name-only -r HEAD | tr '\n' ' ')
branch=$(git rev-parse --abbrev-ref HEAD)

before=$("$KUBECTL" -n "$NS" get deploy,statefulset -o jsonpath='{range .items[*]}{.kind}/{.metadata.name}={.metadata.generation}{"\n"}{end}' 2>/dev/null || true)
echo "deploy: $short \"$subject\" ($branch) -> namespace $NS"
"$KUBECTL" apply -k overlays/prod
after=$("$KUBECTL" -n "$NS" get deploy,statefulset -o jsonpath='{range .items[*]}{.kind}/{.metadata.name}={.metadata.generation}{"\n"}{end}')

changed=""
for line in $after; do
  name="${line%%=*}"
  gen="${line##*=}"
  old=$(printf '%s\n' "$before" | grep "^$name=" | cut -d= -f2 || true)
  if [ "$old" != "$gen" ]; then changed="$changed $name"; fi
done
changed="${changed# }"
for w in $changed; do
  "$KUBECTL" -n "$NS" annotate "$w" "kubernetes.io/change-cause=$short $subject" "shop.example.com/git-sha=$sha" --overwrite >/dev/null
done
echo "deploy: changed workloads: ${changed:-none}"

if [ -n "${LOKI_PUSH_URL:-}" ]; then
  python3 - "$LOKI_PUSH_URL" "$NS" "$sha" "$short" "$subject" "$author" "$committed" "$files" "$changed" "$branch" <<'PY' || echo "deploy: warning: could not record deploy event in Loki" >&2
import json, sys, time, urllib.request
url, ns, sha, short, subject, author, committed, files, changed, branch = sys.argv[1:11]
event = {"event": "deploy", "namespace": ns, "git_sha": sha, "git_short": short, "subject": subject, "author": author,
         "committed_at": committed, "deployed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
         "branch": branch, "changed_files": files.split(), "changed_workloads": changed.split()}
body = {"streams": [{"stream": {"job": "deploy-events", "namespace": ns, "repo": "shop-config"},
                     "values": [[str(time.time_ns()), json.dumps(event)]]}]}
req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
urllib.request.urlopen(req, timeout=10).read()
PY
fi

if [ "$WAIT" = 1 ]; then
  for d in $("$KUBECTL" -n "$NS" get deploy -o name); do
    "$KUBECTL" -n "$NS" rollout status "$d" --timeout=300s
  done
  "$KUBECTL" -n "$NS" rollout status statefulset/postgres --timeout=300s
fi
echo "deploy: done ($short)"

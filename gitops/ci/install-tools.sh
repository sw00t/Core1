#!/usr/bin/env bash
# Install the pinned CI tools (linux amd64) into $1 (default ./.ci-bin), each verified by sha256.
set -euo pipefail
cd "$(dirname "$0")/.."
. ci/versions.env
BIN="${1:-$PWD/.ci-bin}"
mkdir -p "$BIN"
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

fetch() { curl -fsSL --retry 3 --retry-delay 3 -o "$2" "$1"; }
check() { # file expected
  local got; got=$(sha256sum "$1" | awk '{print $1}')
  [ "$got" = "$2" ] || { echo "checksum mismatch for $1: got $got want $2" >&2; exit 1; }
}
sum_for() { awk -v f="$2" '{n=$NF; sub(/^\*/, "", n); sub(/.*\//, "", n); if (n == f) print $1}' "$1"; }

# kustomize
base="https://github.com/kubernetes-sigs/kustomize/releases/download/kustomize%2F${KUSTOMIZE_VERSION}"
f="kustomize_${KUSTOMIZE_VERSION}_linux_amd64.tar.gz"
fetch "$base/$f" "$tmp/$f"; fetch "$base/checksums.txt" "$tmp/k.sums"
check "$tmp/$f" "$(sum_for "$tmp/k.sums" "$f")"
tar -xzf "$tmp/$f" -C "$BIN" kustomize

# kubeconform
base="https://github.com/yannh/kubeconform/releases/download/${KUBECONFORM_VERSION}"
f="kubeconform-linux-amd64.tar.gz"
fetch "$base/$f" "$tmp/$f"; fetch "$base/CHECKSUMS" "$tmp/kc.sums"
check "$tmp/$f" "$(sum_for "$tmp/kc.sums" "$f")"
tar -xzf "$tmp/$f" -C "$BIN" kubeconform

# helm (kustomize renders Helm charts with it)
f="helm-${HELM_VERSION}-linux-amd64.tar.gz"
fetch "https://get.helm.sh/$f" "$tmp/$f"; fetch "https://get.helm.sh/$f.sha256sum" "$tmp/h.sum"
check "$tmp/$f" "$(awk '{print $1}' "$tmp/h.sum")"
tar -xzf "$tmp/$f" -C "$tmp" linux-amd64/helm
install -m 0755 "$tmp/linux-amd64/helm" "$BIN/helm"

# kyverno CLI (policy gate)
base="https://github.com/kyverno/kyverno/releases/download/${KYVERNO_VERSION}"
f="kyverno-cli_${KYVERNO_VERSION}_linux_x86_64.tar.gz"
fetch "$base/$f" "$tmp/$f"; fetch "$base/checksums.txt" "$tmp/ky.sums"
check "$tmp/$f" "$(sum_for "$tmp/ky.sums" "$f")"
tar -xzf "$tmp/$f" -C "$BIN" kyverno

echo "tools in $BIN:"
"$BIN/kustomize" version; "$BIN/kubeconform" -v; "$BIN/helm" version --short; "$BIN/kyverno" version | sed -n 1p  # sed reads to the end; head would SIGPIPE under pipefail

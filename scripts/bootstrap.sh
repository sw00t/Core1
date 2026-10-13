#!/usr/bin/env bash
# Download pinned k3d, kubectl and helm into .bin for this OS/arch.
# Nothing is installed system-wide. Re-running is a no-op when versions match.
. "$(dirname "$0")/lib.sh"

os=$(host_os); arch=$(host_arch)
dl="$WORK/dl"; mkdir -p "$dl"

# fetch URL DEST [ALT_URL...]: tries each URL in turn (IPv4 first, then default), with retries.
fetch() {
  local dest="$2" url; local urls="$1"; shift 2; urls="$urls $*"
  for url in $urls; do
    curl -4 -fsSL --retry 2 --retry-delay 3 --retry-all-errors -o "$dest" "$url" 2>/dev/null && return 0
    curl -fsSL --retry 2 --retry-delay 3 --retry-all-errors -o "$dest" "$url" && return 0
    warn "download failed from $url"
  done
  die "download failed: $1"
}
sha256_of() {
  if command -v sha256sum >/dev/null 2>&1; then sha256sum "$1" | awk '{print $1}'
  else shasum -a 256 "$1" | awk '{print $1}'; fi
}
have() { [ -x "$BIN/$1" ] && [ "$(cat "$BIN/.$1.version" 2>/dev/null)" = "$2" ]; }
mark() { printf '%s' "$2" > "$BIN/.$1.version"; }
check_sum() { # file expected
  local got; got=$(sha256_of "$1")
  [ "$got" = "$2" ] || die "checksum mismatch for $1: got $got want $2"
}

# Escape hatch: point at binaries you already have (e.g. from Homebrew) instead of downloading.
# Set K3D_BIN / KUBECTL_BIN / HELM_BIN in .env. They are copied into .bin so everything else is unchanged.
use_existing() { # name path version
  [ -n "$2" ] || return 1
  [ -x "$2" ] || die "$1: $2 is not executable"
  install -m 0755 "$2" "$BIN/$1"; mark "$1" "$3"; log "$1: using $2"
}
# k3d
if use_existing k3d "${K3D_BIN:-}" "$K3D_VERSION"; then :; elif have k3d "$K3D_VERSION"; then log "k3d $K3D_VERSION present"; else
  log "downloading k3d $K3D_VERSION ($os/$arch)"
  base="https://github.com/k3d-io/k3d/releases/download/$K3D_VERSION"
  fetch "$base/k3d-$os-$arch" "$dl/k3d"
  fetch "$base/checksums.txt" "$dl/k3d.checksums.txt"
  want=$(grep -E "k3d-$os-$arch\$" "$dl/k3d.checksums.txt" | awk '{print $1}' | head -1)
  [ -n "$want" ] || die "k3d checksum for $os/$arch not found in checksums.txt"
  check_sum "$dl/k3d" "$want"
  install -m 0755 "$dl/k3d" "$BIN/k3d"; mark k3d "$K3D_VERSION"
fi

# kubectl
if use_existing kubectl "${KUBECTL_BIN:-}" "$KUBECTL_VERSION"; then :; elif have kubectl "$KUBECTL_VERSION"; then log "kubectl $KUBECTL_VERSION present"; else
  log "downloading kubectl $KUBECTL_VERSION ($os/$arch)"
  base="https://dl.k8s.io/release/$KUBECTL_VERSION/bin/$os/$arch"
  alt="https://cdn.dl.k8s.io/release/$KUBECTL_VERSION/bin/$os/$arch"
  alt2="https://storage.googleapis.com/kubernetes-release/release/$KUBECTL_VERSION/bin/$os/$arch"
  fetch "$base/kubectl" "$dl/kubectl" "$alt/kubectl" "$alt2/kubectl"
  fetch "$base/kubectl.sha256" "$dl/kubectl.sha256" "$alt/kubectl.sha256" "$alt2/kubectl.sha256"
  check_sum "$dl/kubectl" "$(tr -d ' \n' < "$dl/kubectl.sha256")"
  install -m 0755 "$dl/kubectl" "$BIN/kubectl"; mark kubectl "$KUBECTL_VERSION"
fi

# helm
if use_existing helm "${HELM_BIN:-}" "$HELM_VERSION"; then :; elif have helm "$HELM_VERSION"; then log "helm $HELM_VERSION present"; else
  log "downloading helm $HELM_VERSION ($os/$arch)"
  tgz="helm-$HELM_VERSION-$os-$arch.tar.gz"
  fetch "https://get.helm.sh/$tgz" "$dl/$tgz"
  fetch "https://get.helm.sh/$tgz.sha256sum" "$dl/$tgz.sha256sum"
  check_sum "$dl/$tgz" "$(awk '{print $1}' "$dl/$tgz.sha256sum")"
  rm -rf "$dl/helm-x"; mkdir -p "$dl/helm-x"
  tar -xzf "$dl/$tgz" -C "$dl/helm-x"
  install -m 0755 "$dl/helm-x/$os-$arch/helm" "$BIN/helm"; mark helm "$HELM_VERSION"
fi

log "tools ready in $BIN"
"$K3D" version | head -1
"$KUBECTL" version --client 2>/dev/null | head -1
"$HELM" version --short

#!/usr/bin/env bash
# Render every kustomization Argo CD deploys and validate the output. Runs in CI and locally.
# Needs kustomize, kubeconform and helm on PATH.
set -euo pipefail
cd "$(dirname "$0")/.."
. ci/versions.env

out=$(mktemp -d)
trap 'rm -rf "$out"' EXIT
catalog="https://raw.githubusercontent.com/datreeio/CRDs-catalog/${CRDS_CATALOG_COMMIT}/{{.Group}}/{{.ResourceKind}}_{{.ResourceAPIVersion}}.json"
fail=0

for dir in bootstrap platform/*/overlays/*; do
  [ -f "$dir/kustomization.yaml" ] || continue
  file="$out/$(echo "$dir" | tr / _).yaml"
  if ! kustomize build --enable-helm "$dir" > "$file" 2> "$file.err"; then
    echo "FAIL render $dir"; sed 's/^/  /' "$file.err"; fail=1; continue
  fi
  # CRD definitions come from upstream charts and have no schema at this Kubernetes version; resources that use
  # them are still validated against the CRDs catalog.
  if kubeconform -strict -summary -output text -skip CustomResourceDefinition \
      -kubernetes-version "${KUBERNETES_VERSION#v}" \
      -schema-location default -schema-location "$catalog" \
      "$file" > "$file.kc" 2>&1; then
    echo "ok   $dir ($(tail -1 "$file.kc"))"
  else
    echo "FAIL schema $dir"; sed 's/^/  /' "$file.kc"; fail=1
  fi
done

[ "$fail" -eq 0 ] && echo "validate: all good" || echo "validate: failures above"
exit "$fail"

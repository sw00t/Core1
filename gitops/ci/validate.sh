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

for dir in bootstrap platform/*/overlays/* apps/*/overlays/*; do
  [ -f "$dir/kustomization.yaml" ] || continue
  file="$out/$(echo "$dir" | tr / _).yaml"
  if ! kustomize build --enable-helm "$dir" > "$file" 2> "$file.err"; then
    echo "FAIL render $dir"; sed 's/^/  /' "$file.err"; fail=1; continue
  fi
  # Skipped kinds:
  # - CustomResourceDefinition: upstream chart CRDs; no schema at this Kubernetes version. Resources that use
  #   them are still validated against the CRDs catalog.
  # - external-secrets.io/v1 ClusterSecretStore and SecretStore: the catalog schema does not compile in
  #   kubeconform. External Secrets' admission webhook validates them in the cluster.
  skip="CustomResourceDefinition,external-secrets.io/v1/ClusterSecretStore,external-secrets.io/v1/SecretStore"
  if kubeconform -strict -summary -output text -skip "$skip" \
      -kubernetes-version "${KUBERNETES_VERSION#v}" \
      -schema-location default -schema-location "$catalog" \
      "$file" > "$file.kc" 2>&1; then
    echo "ok   $dir ($(tail -1 "$file.kc"))"
  else
    echo "FAIL schema $dir"; sed 's/^/  /' "$file.kc"; fail=1
  fi
  # Policy gate: the Kyverno policies the clusters enforce, applied to what this folder would deploy.
  if kyverno apply policies/baseline.yaml --resource "$file" > "$file.ky" 2>&1; then
    echo "ok   $dir policies"
  else
    echo "FAIL policy $dir"; grep -E "FAIL|fail|validation error|policy .* -> " "$file.ky" | sed 's/^/  /' | head -40; fail=1
  fi
done

echo "== kyverno test policies/tests"
if kyverno test policies/tests > "$out/kyverno-test.txt" 2>&1; then
  echo "ok   $(grep "Test Summary" "$out/kyverno-test.txt")"
else
  echo "FAIL kyverno test"; tail -30 "$out/kyverno-test.txt" | sed 's/^/  /'; fail=1
fi

[ "$fail" -eq 0 ] && echo "validate: all good" || echo "validate: failures above"
exit "$fail"

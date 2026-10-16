# core1-gitops

Desired state for the Core1 lab. Argo CD in the `mgmt` cluster reconciles `mgmt`, `stage` and `prod` from `main`,
polling every 30 s. Every change arrives by pull request; CI (`ci/validate.sh`) must pass first.

## Layout

```
bootstrap/                          root Application, platform AppProject and ApplicationSet
platform/<component>/base           kustomize; Helm charts rendered through helmCharts
platform/<component>/overlays/<c>   one Argo CD Application per folder, deployed to cluster <c>
policies/                           Kyverno policies (enforced in stage and prod, and checked in CI) and tests
ci/                                 pinned CI tools and the validation script
.core1/seed.json                    which Core1 template this content came from
```

## Ownership

Core1 owns `bootstrap/`, `platform/`, `policies/`, `ci/`, `.github/`, `.core1/`, `.gitignore` and this README.
`core1 up` keeps them in step with Core1 through pull requests. Edits made here to those paths are replaced by the
next update.

## Validate locally

```
ci/validate.sh   # needs kustomize, kubeconform, helm and kyverno on PATH
```

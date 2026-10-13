# shop-config

Kubernetes configuration for the shop platform services: `gateway`, `orders`, `inventory`, and the
`postgres` instance orders depends on. Managed with Kustomize.

## Layout

```
base/                      Deployments, Services, StatefulSet. Environment-neutral.
overlays/prod/             What actually runs: image tags, replica counts, resources, config values.
  kustomization.yaml       image tags and replica counts
  config/*.env             per-service configuration (rendered to ConfigMaps)
  patches/*-resources.yaml CPU and memory requests/limits per service
deploy.sh                  the only supported way to apply this repo to a cluster
```

## Making a change

1. Branch from `main`, edit, commit with a message that says why.
2. Open a pull request. Config changes are reviewed like code.
3. After merge, `./deploy.sh` applies `overlays/prod` and records a deploy event.

`deploy.sh` refuses to run with uncommitted changes, so what is deployed is always a commit.

## Conventions

- Image tags are pinned in `overlays/prod/kustomization.yaml`. Never `latest`.
- Configuration values live in `overlays/prod/config/<service>.env`. Changing one rolls the pods
  (the ConfigMap name carries a content hash).
- Secrets are not in this repo. The `orders-db` Secret is provisioned by the platform team.
- Resource requests and limits are in `overlays/prod/patches/`. Memory limits are hard limits:
  a container that exceeds one is killed.
- Probes: `/healthz` is readiness, `/livez` is liveness, on port 8080 for every service.

## Useful commands

```
kubectl kustomize overlays/prod            # render what would be applied
kubectl -n core1-app rollout history deploy # change-cause carries the git commit
git log --oneline                          # the change log
```

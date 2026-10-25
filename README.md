# Core1

Core1 is a reusable, enterprise-shaped lab for interview take-home assignments. A generic platform sits at the core.
Industry packs (telco, retail) layer on top and swap cleanly. The design is in `DESIGN.md`.

No agent code here. `Core1_Incident-Agent` injects scenarios and scores; `Core1_Observability-Agent` responds.
`docs/system.md` draws the line between the three repos.

**Status:** v2 is being built on the `v2` branch, phase by phase (`DESIGN.md` section 13, progress in
`docs/progress.md`). Phases 1 and 2 are in: three clusters, a registry, and the platform core managed by Argo CD
from `core1-gitops`. The working v1 (single cluster, Cascadia Mobile telco skin, five scenarios) is frozen at tag
`v1-frozen`.

## Prerequisites

- macOS on Apple Silicon, Docker Desktop with about 24 GB memory and 8 CPUs (`docs/host.md`)
- Python 3.11 (`brew install python@3.11`), `git`, `curl`
- Two fine-grained GitHub tokens for `core1-gitops` in `.env` (see `.env.example`)

Everything else (k3d, kubectl, helm, kustomize, kubeconform, kyverno, Python packages) is pinned in `versions.env`
and `cli/requirements.txt` and lands in `.bin` and `.venv` inside the repo. Nothing is installed system-wide.
`~/.kube` is never touched.

## Quick start

```
./core1 up              # everything to green; see docs/progress.md for current timings
./core1 status          # clusters, plus Argo CD apps against main HEAD
./core1 status --watch  # the Argo CD view, refreshed every 5 s
./core1 creds           # SSO users and passwords (lab only)
./core1 test smoke      # registry pull, data services, SSO
./core1 nuke            # delete clusters, registry, network, local state (--all also clears caches and the CA)
```

`make help` lists the same commands as Make targets.

## What `up` builds

| Piece | Detail |
|---|---|
| Clusters | `mgmt`, `stage`, `prod`: k3d, 1 server plus 1 agent each, on Docker network `core1` |
| Registry | `k3d-registry`, push to `127.0.0.1:17000`, clusters pull `k3d-registry:17000/<image>` |
| GitOps | `core1-gitops` on GitHub; `up` keeps Core1's `gitops/` template there through PRs merged after CI |
| Argo CD | in mgmt, polls `main` every 30 s, deploys the platform to all three clusters |
| Platform | cert-manager, Envoy Gateway, OpenBao (mgmt), External Secrets, CloudNativePG, Keycloak (mgmt), Kyverno (stage, prod), Postgres, Kafka and Valkey (stage, prod) |
| Local state | `.kube/<cluster>.yaml`, `.work/endpoints.json`, `.ca/` (lab root CA), `.work/openbao/init.json` |

URLs (trust `.ca/ca.crt` to avoid browser warnings, see `docs/host.md`):

| | URL |
|---|---|
| Argo CD | `https://argocd.mgmt.localhost:17181` (log in via Keycloak) |
| Keycloak | `https://sso.mgmt.localhost:17181` |
| OpenBao | `https://bao.mgmt.localhost:17181` |

Host ports bind to 127.0.0.1 only:

| | API | HTTP | HTTPS |
|---|---|---|---|
| mgmt | 17143 | 17180 | 17181 |
| stage | 17243 | 17280 | 17281 |
| prod | 17343 | 17380 | 17381 |

Change the base with `CORE1_PORT_BASE` in `.env` (see `.env.example`).

## Layout

```
core1                 entrypoint: builds .venv, runs the CLI
cli/core1/            the CLI (Typer)
cli/tests/            CLI unit tests (make test)
gitops/               template for core1-gitops: bootstrap, platform components, policies, CI
versions.env          pinned host tools and images; verification in docs/decisions.md
docs/                 system (Core1 and its agents), progress, decisions, host, sizing, v1 inventory, backlog
```

Most other folders are v1 material waiting for their phase. `docs/v1-inventory.md` says what happens to each.
`observability/` is the v1 telemetry stack, not the observability agent. It moves into `gitops/platform/` in phase 3.

# Core1

Core1 is a reusable, enterprise-shaped lab for interview take-home assignments. A generic platform sits at the core.
Industry packs (telco, retail) layer on top and swap cleanly. The design is in `DESIGN.md`.

**Status:** v2 is being built on the `v2` branch, phase by phase (`DESIGN.md` section 13, progress in
`docs/progress.md`). Phase 1 delivers the host layer: three empty k3d clusters and a local registry. The working v1
(single cluster, Cascadia Mobile telco skin, five scenarios) is frozen at tag `v1-frozen`.

## Prerequisites

- macOS on Apple Silicon, Docker Desktop with about 24 GB memory and 8 CPUs (`docs/host.md`)
- Python 3.11 (`brew install python@3.11`), `git`, `curl`

Everything else (k3d, kubectl, helm, Python packages) is pinned in `versions.env` and `cli/requirements.txt` and
lands in `.bin` and `.venv` inside the repo. Nothing is installed system-wide. `~/.kube` is never touched.

## Quick start

```
./core1 up          # registry plus mgmt, stage, prod; about 2 minutes from nothing
./core1 status
./core1 test smoke  # green checks plus an image pull through the registry in every cluster
./core1 nuke        # delete clusters, registry, network, local state (--all also clears caches)
```

`make help` lists the same commands as Make targets.

## What `up` builds

| Piece | Detail |
|---|---|
| Clusters | `mgmt`, `stage`, `prod`: k3d, 1 server plus 1 agent each, Traefik off |
| Network | Docker network `core1`, shared by all clusters and the registry |
| Registry | `k3d-registry`, push to `127.0.0.1:17000`, clusters pull `k3d-registry:17000/<image>` |
| Kubeconfigs | `.kube/mgmt.yaml`, `.kube/stage.yaml`, `.kube/prod.yaml` |
| Endpoints | `.work/endpoints.json` and `.work/endpoints.env` |

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
versions.env          every pinned version; verification in docs/decisions.md
docs/                 progress, decisions, host, sizing, v1 inventory, backlog
```

Most other folders are v1 material waiting for their phase. `docs/v1-inventory.md` says what happens to each.

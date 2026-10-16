# Core1

> **v2 in progress on this branch.** See `DESIGN.md` for the target and `docs/progress.md` for status.
> The working v1 is frozen at tag `v1-frozen`. Parts of this README describe v1 and will be rewritten in phase 1.

In its current skin Core1 plays Cascadia Mobile, a fictional regional mobile operator, and the three services are
its activation platform: gateway (digital channel API), orders (activation orders), inventory (SIM and number stock).

A small, realistic enterprise system you can break on purpose: three services and a database on a
local Kubernetes cluster, with Prometheus, Alertmanager, Grafana and Loki watching them, a config repo
that is the only way changes reach the cluster, and five scripted incidents with one-command reset.

Core1 is the reusable base. The agent, its tools and the evaluation harness live in a separate repo and
talk to Core1 only through standard APIs (Prometheus, Loki, Alertmanager webhooks, the Kubernetes API with
a read-only identity, and git).

## Prerequisites

- Docker engine running (Docker Desktop on macOS: at least 8 GB memory allocated)
- `make`, `bash`, `git`, `curl`, `tar` (all present on macOS and most Linux)
- `python3` 3.9 or newer, standard library only (macOS ships one with the developer tools)

Everything else (k3d, kubectl, helm) is downloaded into `.bin/` at pinned versions. Nothing is installed
system-wide; `~/.kube` and other clusters are never touched.

## Quick start

```
cp .env.example .env        # optional; defaults work
make up                     # 10 to 20 minutes the first time
make status
make verify-quick           # about 2 minutes
make verify                 # full run with every scenario, 30 to 45 minutes
```

Then open Grafana at the URL in `.work/endpoints.env` (admin / the password in `.env`).

## Commands

```
make up / down / reset      build everything; delete it; return to the known-good baseline
make status                 one-screen summary (pods, config repo log, active lab alerts, disk)
make scenario N=3           inject scenario 3 (see make scenarios)
make verify / verify-quick  acceptance tests; reports land in reports/
make diag                   diagnostics bundle into logs/diag-<timestamp>/
make help                   everything else
```

## What is in the box

| Piece | Where | Notes |
|---|---|---|
| Cluster | k3d, one node, name `core1` | ports bound to 127.0.0.1 only; see `.env.example` |
| Services | `services/app` | gateway, orders (Postgres), inventory; FastAPI; Prometheus metrics; JSON logs with trace ids |
| Load | `cluster/lab-system.yaml` | steady synthetic traffic, default 40 rps |
| Metrics and alerts | `observability/` | kube-prometheus-stack; lab rules in `rules/`; one dashboard |
| Logs | `observability/loki`, `observability/alloy` | plain manifests, 24h retention |
| Config repo | `config-repo-template/` seeded into `.work/config-repo` | Kustomize; `deploy.sh` is the only write path; commit stamped on workloads; deploy events in Loki |
| Scenarios | `scenarios/scenarios.json` | 4 change-caused faults, 1 decoy, each with an answer file |
| Read-only identity | `rbac/agent-readonly.yaml` | `.kube/agent-readonly.yaml` for the agent; no secrets, no writes |
| Endpoints | `.work/endpoints.env` | every URL and path the agent layer needs |

## Scenarios

| N | Fault | How it shows up |
|---|---|---|
| 1 | orders memory limit cut to 32Mi | OOMKilled, CrashLoopBackOff, rollout stuck |
| 2 | inventory image tag that was never built | ImagePullBackOff, rollout stuck |
| 3 | gateway readiness probe path changed | pods Running but never Ready, rollout stuck |
| 4 | orders DB pool capped at 1 | 503s and high latency on orders and gateway |
| 5 | decoy: inventory slowed at runtime, no change anywhere | p95 latency alert with no matching commit or deploy |

`make scenario N=4` commits and deploys the change (or flips the runtime fault). `make reset` restores
the baseline. Answer files: `scripts/scenario.py expected N`.

## Interfaces for the agent layer

- Alerts: Alertmanager posts lab alerts (label `lab=core1`) to `ALERT_WEBHOOK_URL` (`.env`). Default is the
  in-cluster sink; point it at `http://host.k3d.internal:PORT/...` for an agent on your host.
- Metrics: Prometheus HTTP API. Logs: Loki HTTP API (`{namespace="core1-app", app="orders"}`,
  `{job="deploy-events"}`). Both URLs are in `.work/endpoints.env`.
- Cluster: `.kube/agent-readonly.yaml` (get/list/watch; no secrets; no writes).
- Changes: the config repo at `.work/config-repo`. `deploy.sh` applies HEAD and records a deploy event.

## Portability

Clone on another machine with Docker, run `make up`. Versions are pinned in `versions.env`; ports and sizes
in `.env`. Tested target: Apple Silicon macOS. Linux amd64/arm64 should work unchanged (not yet verified).
Windows: WSL2 only, untested. Memory estimate 6 to 8 GB, disk 10 to 15 GB (ceiling enforced by
`DISK_CEILING_GB`).

More: `DESIGN.md` (v2 design), `docs/v1-inventory.md` (what happens to each v1 file), `docs/DEVELOPING.md`
(services and tests).

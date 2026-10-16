# v1 inventory

Every tracked v1 file and Make target, marked for v2. v1 is frozen at tag `v1-frozen` (`b35f275`). Anything
deleted here stays reachable there.

## Marks

- **keep**: carries into v2 mostly as is.
- **rewrite (N)**: v2 needs an equivalent. The v1 file stays until its replacement lands in phase N.
- **delete now**: no v2 role and nothing that stays references it. Removed in the phase 0 commit.
- **delete (N)**: no v2 role, but files that stay still call it. Removed in phase N together with its callers.

Phase numbers refer to `DESIGN.md` section 13.

## Root and docs

| Path | Mark | Reason |
|---|---|---|
| `.gitignore` | keep | Same local-state dirs. Extend in phase 1 |
| `.env.example` | rewrite (1) | Single-cluster ports, 20 GB disk ceiling, and a default Grafana password break the v2 security baseline |
| `Makefile` | rewrite (1) | Becomes a thin shim over `core1` |
| `versions.env` | rewrite (1) | Format kept. Every entry re-verified and recorded in `docs/decisions.md` |
| `README.md` | rewrite (1) | Cascadia narrative moves to the telco pack. Phase 0 adds a v2 banner only |
| `docs/DESIGN.md` (v1) | delete now | Superseded by root `DESIGN.md`. Rationale worth keeping is below |
| `docs/RUNNER.md` | delete now | The runner served a remote helper with file-only access. Claude Code now runs on the host |
| `docs/TRACING.md` | delete now | Superseded. Tempo and OTel are in scope in phase 3 |
| `docs/DEVELOPING.md` | rewrite (5) | Dev guide for the neutral reference app |
| `docs/TROUBLESHOOTING.md` | rewrite (1) | Host tips still apply (registry.k8s.io CDN block, containerd image import, file modes). Fold into `docs/host.md` |
| `reports/verify-*.md` (6 files) | delete now | Generated v1 run output, not source |

## Scripts

| Path | Mark | Reason |
|---|---|---|
| `scripts/lib.sh` | rewrite (1) | Helpers move into the Python CLI: pinned tools on PATH, repo-local KUBECONFIG and Helm homes, `wait_pods`, `wait_http` |
| `scripts/bootstrap.sh` | rewrite (1) | Checksummed pinned downloads into `.bin` carry into `core1`. Used as is for the phase 0 spike |
| `scripts/doctor.sh` | rewrite (1) | `core1 doctor` |
| `scripts/cluster-up.sh` | rewrite (1) | Three clusters plus the local registry in `core1 up` |
| `scripts/cluster-down.sh` | rewrite (1) | `core1 nuke` |
| `scripts/clean.sh` | rewrite (1) | `core1 nuke` |
| `scripts/build-images.sh` | rewrite (5) | Push to the local OCI registry instead of `k3d image import`. Moved from phase 1: no images to build until the neutral app |
| `scripts/disk_check.py` | delete (1) | v2 removes the disk ceiling. Still called by doctor, status, diag and verify |
| `scripts/runner.sh` | delete now | See `docs/RUNNER.md`. The `runner` Make target goes with it |
| `scripts/endpoints.sh` | rewrite (1, 8) | `core1 endpoints` and the `.work/endpoints.json` contract |
| `scripts/status.sh` | rewrite (1) | `core1 status` |
| `scripts/wait-green.sh` | rewrite (1) | The green gate at the end of `core1 up` |
| `scripts/diag.sh` | rewrite (backlog) | Useful, but not in the `DESIGN.md` CLI list. Logged in `docs/backlog.md` |
| `scripts/obs-install.sh` | rewrite (3) | Argo CD managed in v2. Keep the `prepull_via_host` workaround |
| `scripts/app-secrets.sh` | delete (2) | Replaced by OpenBao plus External Secrets |
| `scripts/config-repo-init.sh` | rewrite (6, 7) | Local config repo replaced by `core1-gitops` on GitHub |
| `scripts/seed_history.py` | rewrite (6, 7) | History seeding reused for pack history and scenario noise commits |
| `scripts/deploy.sh` | delete (2) | Argo CD replaces it |
| `scripts/reset.sh` | rewrite (1 to 8) | Becomes the reset tiers. Its `push-main --force` to the config repo remote must not carry over |
| `scripts/loadgen.sh` | delete (6) | Traffic generator runs in mgmt |
| `scripts/agent-kubeconfig.sh` | rewrite (8) | Read-only identity per cluster |
| `scripts/scenario.py` | rewrite (7) | Scenario engine. The `kubectl exec` fault switch becomes the `fault-endpoint` injection path |
| `scripts/gen_dashboard.py` | rewrite (3, 6) | Core dashboard generator plus pack dashboard generators |

## Manifests and config

| Path | Mark | Reason |
|---|---|---|
| `cluster/lab-system.yaml` | delete (4, 6) | loadgen replaced by the traffic generator, alert-sink by the paging mock sink |
| `rbac/agent-readonly.yaml` | keep | Rules already match the v2 contract (no secrets, no exec, no writes). Namespace and per-cluster wiring change in phase 8 |
| `observability/kube-prometheus-stack-values.yaml` | rewrite (3) | Split into the mgmt receiver and agent-mode senders in stage and prod |
| `observability/loki/loki.yaml` | rewrite (3) | Moves to mgmt. Retention follows the `DESIGN.md` section 11 trim order |
| `observability/alloy/alloy.yaml` | rewrite (3) | Ships logs from stage and prod to mgmt. Adds an OTLP receiver |
| `observability/nodeports.yaml` | delete (3) | Gateway API replaces NodePorts |
| `observability/app-servicemonitor.yaml` | keep | Label-based scrape pattern carries. Namespaces change |
| `observability/rules/core1-alerts.yaml` | rewrite (3, 6) | Workload alerts go to core, plus SLO burn-rate rules. `cascadia:*` recording rules go to the telco pack |
| `observability/dashboards/core1-services.yaml` | rewrite (3, 6) | Generated file. Generic panels go to core, the activations row to the telco pack |
| `config-repo-template/base/*.yaml` | rewrite (5) | Neutral app manifests in `core1-gitops` |
| `config-repo-template/overlays/prod/**` | rewrite (5, 6) | Env overlays in `core1-gitops`. Telco values move to pack overlays |
| `config-repo-template/deploy.sh` | delete (2) | Argo CD replaces it. Port the idea: deploy events in Loki and change-cause annotations |
| `config-repo-template/change-freeze.json` | rewrite (4, 6) | Freeze windows become ITSM mock data. The telco window moves to the pack |
| `config-repo-template/README.md` | rewrite (6) | Telco narrative for the pack README |
| `config-repo-template/.gitignore` | rewrite (6) | Goes with the template |
| `config-repo-seed/history.json` | rewrite (6) | Telco lived-in history moves to the telco pack |
| `scenarios/scenarios.json` | rewrite (7) | The five scenarios become telco pack YAML, decoy included |

## Services and tests

| Path | Mark | Reason |
|---|---|---|
| `services/app/core1app/common.py` | keep | JSON logs, Prometheus metrics, `traceparent` propagation, upstream error mapping. Base of the reference app. Add OTel |
| `services/app/core1app/__init__.py`, `__main__.py` | keep | One package, service chosen by `CORE1_SERVICE` |
| `services/app/Dockerfile` | keep | One image for every service |
| `services/app/core1app/gateway.py` | rewrite (5) | Becomes `edge-gateway` |
| `services/app/core1app/orders.py` | rewrite (5) | Neutral `orders`. Pool metrics and the in-memory store carry |
| `services/app/core1app/inventory.py` | rewrite (5, 6) | Becomes `resource-store`. ICCID and MSISDN generation move to the telco pack |
| `services/app/core1app/loadgen.py` | rewrite (6) | Traffic generator. The telco mix becomes the pack traffic profile |
| `services/app/core1app/alert_sink.py` | rewrite (4) | The sink role moves to the paging mock |
| `services/app/requirements.txt`, `requirements-dev.txt` | rewrite (5) | Re-verify pins. Add OTel |
| `services/app/tests/*` | rewrite (5) | Follow the services |
| `tests/verify.py` | rewrite (1, 8) | `core1 test smoke` and the acceptance run |

## Make targets

| Target | Mark | v2 home |
|---|---|---|
| `help` | keep | Stays in the shim |
| `doctor`, `bootstrap` | rewrite (1) | `core1 doctor` (bootstrap folds into `up`) |
| `up`, `cluster`, `images`, `obs`, `wait-green` | rewrite (1) | `core1 up` |
| `down`, `clean` | rewrite (1) | `core1 nuke` |
| `reset` | rewrite (1 to 8) | `core1 reset scenario/pack/app/platform` |
| `status` | rewrite (1) | `core1 status` |
| `endpoints` | rewrite (1) | `core1 endpoints` |
| `agent-kubeconfig` | rewrite (8) | Part of `core1 up` and the contract |
| `scenario`, `scenarios`, `scenario-1` to `scenario-5` | rewrite (7) | `core1 scenario list/run` |
| `verify`, `verify-quick`, `test` | rewrite (1, 8) | `core1 test smoke/all` |
| `diag` | rewrite (backlog) | Candidate `core1 diag` |
| `disk` | delete (1) | Disk ceiling removed |
| `push` | delete (1) | Plain `git push` |
| `secrets`, `config-repo`, `deploy` | delete (2) | OpenBao, `core1-gitops`, Argo CD |
| `loadgen` | delete (6) | Traffic generator |
| `runner` | delete now | Runner removed |

## Telco-specific content for `packs/telco/`

- Cascadia Mobile narrative: root `README.md` intro, `config-repo-template/README.md`.
- Seeded history: `config-repo-seed/history.json` (number-port batch, device launch weekend, plan catalogue).
- Freeze window "Q4 device launch weekend" in `change-freeze.json`.
- The five scenarios in `scenarios/scenarios.json`, with their commit authors and messages, and the decoy.
- Recording rules `cascadia:activations_per_min`, `cascadia:failed_activations_per_min`.
- Dashboard title "Cascadia Mobile / Activation platform", the activations row, `cascadia` tag.
- `inventory.py`: ICCID and MSISDN generation, `PLAN-xxx` codes, "no SIM stock" message.
- `loadgen.py`: activate, order status, list plans mix; channels app, web, retail.
- Docstrings in `gateway.py` and `orders.py` (activation orders, retail POS).
- `app.kubernetes.io/part-of: activation-platform` label in the config template.
- `deploy.sh`: `cascadia.example/git-sha` annotation and `repo=cascadia-activation-config` Loki label.
- `services/app/tests/test_orders.py`: ICCID and MSISDN fixtures.

## Out of scope reference

`scripts/reset.sh` and `scripts/scenario.py push-main` push the local config repo to its `origin` when one is set.
In v1 that remote was `cascadia-activation-config`, which belongs to the paused Core1-agent. v2 does not use it.

## Rationale carried from v1 `docs/DESIGN.md`

- No agent code in the base. Agents consume Prometheus, Loki, Alertmanager webhooks, read-only Kubernetes, and git.
- Loki and Alloy as plain manifests: small enough to read in one sitting, no production chart defaults.
- Alloy over Promtail: Promtail reached end of life in 2026.
- Secrets live outside the config repo, so the read-only identity and the repo hold none.
- Scenario commits read like ordinary history. Answer files live outside the repo the agent sees.
- Short alert windows (1m) and a 15s scrape interval give fast lab feedback. Not production values.
- Each deploy is recorded three ways: git log, rollout change-cause, and a Loki deploy event.
- v1 "done" bar: `make down && make up && make verify` passes twice in a row.

## Phase 0 deletions and edits

Deleted: `docs/DESIGN.md`, `docs/RUNNER.md`, `docs/TRACING.md`, `scripts/runner.sh`, `reports/verify-*.md`.

Edited: `runner` target removed from `Makefile`. `README.md` gets a v2 banner and loses links to deleted docs.
`observability/alloy/alloy.yaml` loses its pointer to `docs/TRACING.md`.

## Phase 1 deletions and edits

Replaced by the `core1` CLI and deleted: `scripts/bootstrap.sh`, `scripts/doctor.sh`, `scripts/cluster-up.sh`,
`scripts/cluster-down.sh`, `scripts/clean.sh`, `scripts/status.sh`, `scripts/wait-green.sh`, `scripts/endpoints.sh`,
`scripts/disk_check.py`, `docs/TROUBLESHOOTING.md` (folded into `docs/host.md`).

Rewritten: `Makefile` (shim over `./core1`), `versions.env` (v2 pins only), `.env.example`, `README.md`, `.gitignore`.

v1 scripts still in the tree (`lib.sh`, `obs-install.sh`, `deploy.sh`, `reset.sh`, `scenario.py`, `diag.sh`,
`tests/verify.py` and others) are reference only. Nothing calls them, and some point at files removed above. Each
goes when its phase lands.

## Phase 2 deletions

Replaced by the platform core and deleted: `scripts/app-secrets.sh` (OpenBao plus External Secrets),
`scripts/deploy.sh` and `config-repo-template/deploy.sh` (Argo CD). The deploy-event idea (a record of every change
that reached a cluster) is still to be ported; Argo CD's sync history and the core1-gitops log cover it for now.

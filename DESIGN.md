# Core1 v2 design

Status: approved direction, pre-build. Owner: S. Build tool: Claude Code (Desktop or CLI) on macOS.

## 1. Purpose

Core1 becomes a reusable, enterprise-realistic base for interview take-home assignments. A generic enterprise
platform sits at the core. Industry verticals (telco, retail, finance, and others later) are packs layered on top that
install, remove, and swap cleanly. Packs and scenarios can be blown away and rebuilt for reps, rehearsals, tests, and
experiments.

Out of scope: Core1-agent. It stays paused and untouched. Core1 v1 is tagged before any change so Core1-agent can
keep pinning it.

## 2. Decisions

| Area | Decision | Notes |
|---|---|---|
| Repo strategy | Refactor Core1 in place | Tag current main first (proposed tag: `v1-frozen`), work on a `v2` branch, merge when acceptance passes |
| Git host | GitHub only | Platform source, GitOps desired state, PRs, CI (GitHub Actions) all on GitHub |
| Default profile | Full | Management cluster plus stage plus prod. A lite profile exists as a fallback, not the default |
| Container runtime | Docker Desktop | Most recognizable to enterprise audiences. See section 11 |
| Second pack | Retail | Telco plus retail ship together to prove the pack seam |
| Language | Python | Services, mocks, CLI, traffic generator, scenario engine |
| Target host | M3 Pro, 36 GB RAM, macOS Tahoe, up to 600 GB disk | The v1 20 GB disk ceiling is removed |

Open items (confirm with S before building the affected phase):
- GitHub owner and the name of the new GitOps repo (proposed: `core1-gitops`).
- Repo visibility (public or private). Branch protection and rulesets on private repos may need a paid GitHub plan; verify.
- Whether to archive or leave `cascadia-activation-config`. Default: leave untouched, it belongs to the paused Core1-agent.

## 3. Principles

1. The core knows orders, entities, SLOs, changes, and incidents. It knows nothing about any industry.
2. A vertical pack is data plus skins: vocabulary, business KPI, traffic shape, dependency stubs, faults, dashboards,
   compliance rules.
3. Removing a pack returns the system to the core baseline, proven by an automated test.
4. Every layer has its own reset. Reps are cheap.
5. Agent-agnostic. Any take-home solution plugs into a stable contract (section 9).
6. Production-shaped paths only. Changes go through PRs and GitOps, never direct apply, except the scenario engine's
   explicitly labelled fault injection.
7. Pinned, reproducible, idempotent. A clean clone on macOS reaches green with one command.

## 4. Layer model

| Layer | Contents | Reset | Reset target (to validate) |
|---|---|---|---|
| L0 Host | Docker Desktop VM, pinned toolchain in `.bin`, profile | `core1 nuke` then `core1 up` | Full rebuild |
| L1 Platform | Clusters, GitOps, identity, secrets, policy, observability, ITSM and paging mocks | `core1 reset platform` | Longest |
| L2 Reference app | Vertical-neutral transaction pipeline | `core1 reset app` | A few minutes |
| L3 Vertical pack | Skin, data, traffic, scenarios | `core1 pack remove` / `swap` | 1 to 2 minutes |
| L4 Scenario run | One injected fault plus ground truth | `core1 reset scenario` | Seconds |

## 5. Topology

Three k3d clusters inside Docker Desktop:

- `mgmt`: Argo CD, Keycloak, OpenBao, External Secrets controller, central Prometheus (receiver), Alertmanager, Loki,
  Tempo, Grafana, ITSM mock, paging mock, local OCI registry, traffic generator, scenario engine.
- `stage` and `prod`: the reference app, CloudNativePG Postgres, Redpanda, Valkey, Kyverno, cert-manager, Gateway API
  controller, Prometheus in agent mode remote-writing to mgmt, OTel Collector, Promtail or Alloy shipping to mgmt.

Promotion path: PR to `core1-gitops` targets stage, a promotion PR copies the version to prod. Argo CD in mgmt
reconciles both workload clusters by polling GitHub (webhooks cannot reach the laptop without a tunnel; set a short
poll interval).

## 6. Platform components (L1)

Candidates. Claude Code verifies current maintenance status, licensing, and arm64 images for each, then pins versions
in `versions.env` before installing. Swap any that fail verification and record why in `docs/decisions.md`.

| Capability | Candidate | Enterprise analogue it stands in for |
|---|---|---|
| GitOps | Argo CD with ApplicationSets | Argo CD, Flux, Harness |
| CI | GitHub Actions on `core1-gitops` PRs: kustomize build, kubeconform, Kyverno CLI tests | Enterprise CI gates |
| Identity | Keycloak, OIDC SSO into Grafana and Argo CD | Okta, Entra ID |
| Secrets | OpenBao (or Vault) plus External Secrets Operator | Vault, cloud secret managers |
| Policy | Kyverno at admission and in CI | OPA Gatekeeper, Kyverno |
| Ingress | Gateway API controller (for example Envoy Gateway) | Cloud load balancers, API gateways |
| Certificates | cert-manager with an internal CA | Enterprise PKI |
| Database | CloudNativePG, treated as a managed service | RDS, Cloud SQL |
| Event bus | Redpanda (Kafka API) | Kafka, MSK, Confluent |
| Cache | Valkey | Redis, ElastiCache |
| Metrics and alerts | Prometheus, Alertmanager, SLO burn-rate rules (Sloth or Pyrra) | Datadog, Prometheus estates |
| Logs | Loki | Splunk, Elastic |
| Traces | Tempo plus OTel Collector | Datadog APM, Dynatrace |
| Dashboards | Grafana, provisioned from code | Grafana, Datadog |
| ITSM | Python mock, ServiceNow-style table API: change, incident, CAB class, approval | ServiceNow, Jira Service Management |
| Paging | Python mock: schedules, escalation, routing, maintenance silences, outbound webhook | PagerDuty, Opsgenie |
| Registry | Local OCI registry (GHCR optional later) | Artifactory, ECR |

Security baseline: no default admin passwords, SSO everywhere it is supported, short-lived tokens, read-only
identities cannot read secrets, NetworkPolicies default deny in app namespaces, GitHub token is fine-grained and scoped
to the two repos, stored in OpenBao.

## 7. Reference app (L2)

One Python codebase (FastAPI services, OpenTelemetry instrumented), one image set. Vertical-neutral names in code;
packs supply display names, labels, and behaviour profiles.

| Service | Role |
|---|---|
| edge-gateway | Public entry, auth, rate limits, routes sync calls |
| accounts | Customer and account records (synthetic, masked) |
| catalog | Products or plans |
| orders | Accepts orders, writes Postgres, emits events |
| orchestrator | Saga over the event bus, retries, compensation |
| fulfillment-adapter | Calls external dependency stubs |
| resource-store | Inventory of allocatable things |
| ledger | Charges, payments, balances |
| notifications | Outbound messages |
| dependency-stubs | Configurable fake third parties with latency and error profiles |

Mapping examples:

| Concept | Telco pack | Retail pack |
|---|---|---|
| Order | SIM activation | Checkout |
| Fulfillment | HSS/UDM provisioning, eSIM SM-DP+ | Warehouse pick, carrier label |
| Resource | SIM, MSISDN | Stock units |
| Business KPI | Activations per minute, failed activations | Checkouts per minute, failed checkouts |
| Data rule | CPNI masking | PCI and PII masking |
| Surge event | Device launch | Flash sale |

## 8. Pack contract (L3)

A pack is a folder: `packs/<id>/`.

```
packs/<id>/
  pack.yaml            id, version, display name, vocabulary map, KPI and SLO definitions,
                       protected paths, change classes, masking rules
  overlays/            kustomize patches over the neutral app (names, env, replicas, stubs)
  data/                synthetic data generator config and seed
  traffic/             diurnal curve, channel mix, surge events
  dashboards/          Grafana dashboard generators
  alerts/              PrometheusRules and SLOs for the business KPI
  scenarios/           scenario definitions (section 10)
  README.md            the narrative skin for demos
```

Mechanics:
- Each installed pack is one Argo CD Application per environment, generated by an ApplicationSet.
- Every resource carries `core1.io/pack: <id>`. Pack data lives in pack-owned schemas or tables.
- Remove: delete the Application with prune, drop pack data, reseed the neutral baseline.
- Swap: remove then install, one command.
- Proof test (`core1 test pack-seam`): install telco, remove, assert zero resources with the label and an empty diff
  against the core baseline; repeat for retail; then swap telco to retail and back.

The neutral baseline (no pack installed) must run green on its own with generic names.

## 9. Agent-facing contract

Stable seams for any take-home solution. Documented in `docs/contract.md` and versioned.

- `.work/endpoints.json` and `.env`: every URL, kubeconfig path, repo URL.
- Read-only identity per cluster: get, list, watch on workloads, logs, events, config; no secrets, no exec.
- Change path: PR to `core1-gitops`. Nothing else may change desired state.
- ITSM API: create and update incidents, query changes, request approval.
- Alert webhook: Alertmanager and the paging mock post to a configurable sink URL.
- Telemetry query APIs: Prometheus, Loki, Tempo through Grafana or directly.
- Scenario ground truth files for evals.

## 10. Scenario engine and fault library (L4)

Generic primitives, parameterized, bound to vertical narratives by packs:
config edit, resource limit, image tag, connection pool cap, dependency latency, dependency error rate, certificate
expiry, DNS failure, feature flag flip, schema migration, cluster partition, queue lag.

Noise options: unrelated commits near the fault, flapping alerts, a planned maintenance silence, true decoys with no
change. Default noise level is a per-run flag.

Scenario file (YAML) fields: id, pack, primitive, parameters, injection path (`pr` through GitHub plus ITSM change
ticket, or `fault-endpoint` for non-change faults), expected alerts, ground truth (cause, correct action, acceptable
alternatives, must-escalate flag), cleanup.

Traffic generator: Python (Locust or an asyncio generator, decide in phase 6), driven by the pack traffic profile.

Port the five v1 Cascadia scenarios into the telco pack as the first set, including the decoy.

## 11. Host and runtime

Docker Desktop is the most widely recognized runtime in enterprise settings, so it stays. Note for audiences: Docker
Desktop needs a paid subscription for larger commercial organizations; personal and small-business use is free.
OrbStack or Colima are the fallback if VM performance becomes the bottleneck.

Settings to apply and record in `docs/host.md`: VM memory around 24 GB (leave the rest for macOS), CPU 8 or more,
disk image size raised well above the default. k3d stays (pinned in `.bin`) because it handles three clusters cleanly;
Docker Desktop's built-in Kubernetes is not used.

Sizing figures are estimates until phase 0 measures them. If the full profile does not fit in about 24 GB, trim in
this order: Tempo retention, Loki retention, single-replica everything in stage, then consider merging stage into prod
namespaces.

## 12. CLI

One entrypoint, `core1`, written in Python (Typer). The Makefile remains as a thin shim for muscle memory.

```
core1 doctor                      host checks, versions, ports, VM resources
core1 up [--profile full|lite]    idempotent bring-up to green
core1 status                      clusters, Argo CD sync, alerts, KPI
core1 pack list|install|remove|swap <id>
core1 scenario list|run <id> [--noise low|med|high]
core1 reset scenario|pack|app|platform
core1 nuke                        delete clusters and local state
core1 endpoints                   regenerate the contract files
core1 test pack-seam|smoke|all
```

## 13. Build phases and exit criteria

Each phase ends with a commit on `v2`, a short entry in `docs/progress.md`, and a demo of its exit criteria to S.

| Phase | Scope | Exit criteria |
|---|---|---|
| 0 Prep and spike | Tag `v1-frozen`, create `v2`, inventory v1, configure Docker Desktop, bring up three empty k3d clusters, measure | Tag pushed; `docs/sizing.md` with measured idle RAM and disk; `docs/v1-inventory.md` listing keep, rewrite, delete |
| 1 Host and CLI | `core1` CLI skeleton, `versions.env`, `doctor`, `up` and `nuke` for clusters and registry | Clean clone to three green clusters with one command; `nuke` leaves nothing behind |
| 2 Platform core | Argo CD, `core1-gitops` repo and CI, Keycloak, OpenBao plus ESO, cert-manager, Gateway API, Kyverno, CNPG, Redpanda, Valkey | Argo CD shows all platform apps synced in stage and prod; SSO works; a policy-violating PR fails CI |
| 3 Observability | Prometheus agents to mgmt, Alertmanager, Loki, Tempo, OTel, Grafana from code, SLO rules | One Grafana shows metrics, logs, and traces from both clusters |
| 4 ITSM and paging mocks | Python services with table-style APIs | Change and incident lifecycle via API; Alertmanager pages through the mock to a sink |
| 5 Neutral reference app | Ten services, events, saga, stubs, neutral baseline | Neutral app green in stage and prod; promotion PR flow works end to end |
| 6 Pack system | Pack loader, telco pack (port v1), retail pack, traffic generator | `core1 test pack-seam` passes; both packs show their business KPI dashboards |
| 7 Scenario engine | Primitives, noise, ground truth, both injection paths | v1 scenarios 1 to 5 reproduce in telco; at least three retail scenarios; decoy produces no correlated change |
| 8 Hardening and handoff | Reset tiers, read-only identities, contract docs, smoke tests | Fresh-clone acceptance run passes; reset timings recorded; `docs/contract.md` complete |

## 14. Risks and verifications

- Footprint of the full profile on 24 GB VM memory. Measured in phase 0 and phase 3; trim order in section 11.
- arm64 image availability for every component. Verify before pinning.
- Component maintenance and licence changes. Verify each candidate at build time and record in `docs/decisions.md`.
- GitHub polling latency for Argo CD affects demo timing. Measure and document.
- Private repo branch protection may need a paid plan. Decide visibility before phase 2.
- Scope creep. The phases are the scope. Anything else goes in `docs/backlog.md`.

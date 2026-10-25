# Core1 and its agents

Three repos, three jobs. This file is the line between them. The other two repos link here.

| Repo | Job | One line |
|---|---|---|
| `Core1` | The platform | Generic enterprise system you can break on purpose. Knows nothing about any agent |
| `Core1_Incident-Agent` | The examiner | Picks a scenario, injects it, holds the answer key, scores the response, cleans up the fault |
| `Core1_Observability-Agent` | The responder | Always on. Watches, decides what is an incident, investigates, remembers, opens PRs, audits the evaluators |

Decided with S on 2026-10-25. Before that date `Core1_Incident-Agent` (then `Core1-agent`) was the responder. That
code moves to `Core1_Observability-Agent`. The working v1 pairing stays reachable: Core1 tag `v1-frozen` with
Core1_Incident-Agent tag `v1-frozen`.

## Who owns what

| Concern | Core1 | Incident-Agent | Observability-Agent |
|---|---|---|---|
| Clusters, GitOps, identity, secrets, policy | owns | | |
| Telemetry stack: Prometheus, Alertmanager, Loki, Tempo, Grafana | owns | | reads |
| Alert rules and SLOs | owns (core and pack rules) | reads after a run | audits, proposes changes by PR |
| Reference app and packs (vocabulary, KPI, traffic, dashboards) | owns | reads pack ids | reads KPI definitions |
| Fault primitives and the labelled injection endpoint | owns | calls | never calls |
| Scenario catalog, noise, ground truth | | owns | never reads during a run |
| Starting and ending a scenario run, fault cleanup | `core1 reset scenario` | owns the run | |
| Triggers: what counts as an incident | | | owns |
| Investigation, policy, review, fix PRs | | | owns |
| Durable memory of past incidents | | | owns |
| Scoring a response against ground truth | | owns | |
| Evaluating the evaluators | | | owns, read-only on scores |
| Sandbox cleanup: branches, PRs, scratch namespaces, workspaces | its own reset tiers | its own scenario leftovers | its own artifacts, and reports anyone's orphans |

## How they connect

```
              injects (PR + ITSM change, or fault endpoint)
Incident-Agent ─────────────────────────────────────────────▶ Core1
      ▲                                                          │
      │ incident records (after the run closes)                  │ alerts, metrics, logs, traces,
      │                                                          │ Argo CD, ITSM, read-only k8s
      │ sealed scorecards (after the run closes)                 ▼
      └──────────────────────────────────────────── Observability-Agent
                                                         │
                                                         └▶ PRs to core1-gitops, ITSM updates, pages
```

- The two agents never talk during a run. Incident-Agent breaks Core1. Observability-Agent finds out the way an
  on-call engineer would, through Core1's telemetry and change records.
- Core1 sees both agents only through its contract (`DESIGN.md` section 9, `docs/contract.md` from phase 8).
- After a run closes, Incident-Agent reads Observability-Agent's incident record and scores it. The scorecard is sealed.
- Observability-Agent may then read sealed scorecards to audit the scoring. It cannot edit a score or a ground truth.

## Rules that hold the line

1. Core1 contains no agent code and no ground truth. Fault primitives are mechanism. What a fault means, and the right
   answer, live in Incident-Agent.
2. Observability-Agent never reads ground truth before a run is sealed. On one laptop this is a convention plus a tool
   allowlist, so it gets a test: a run fails if the responder's audit log touches Incident-Agent paths.
3. Only Observability-Agent proposes fixes. Only a human merges. No agent applies a change to a cluster.
4. Only Incident-Agent injects faults, and only through Core1's labelled paths. Every injection carries
   `core1.io/scenario: <run id>` so it is visible to the platform, cleanable, and excluded from fix attribution in
   scoring.
5. Each repo cleans up what it creates. Observability-Agent also reports orphans it did not create; it does not delete
   them.
6. Evaluators are audited by a party that cannot change them. Observability-Agent is graded by Incident-Agent, so its
   meta-eval is read-only and every finding goes to S as a report or a PR.

## Evaluating the evaluators

Three evaluators, all audited by Observability-Agent:

| Evaluator | Owner | What the audit checks |
|---|---|---|
| Run scorer | Incident-Agent | Re-scores a sample of sealed runs; flags scorer bugs, disagreement with ground truth, unstable scores across repeat runs |
| Reviewer agent | Observability-Agent | Review verdict against the outcome: approved fixes that failed recovery, rejected fixes that were right |
| Alert rules and SLOs | Core1 | Per scenario: detected or missed, time to detect, false alarms outside runs; proposes rule changes by PR |

## Naming

- `Core1/observability/` (v1) is the telemetry stack, not the agent. In v2 it folds into `gitops/platform/` in
  phase 3 (`docs/v1-inventory.md`). The name clash ends there.
- Repos follow `Core1_<Role>-Agent`. The lab name `Core1`, `CORE1_*` settings and `core1-*` namespaces do not change.

## Order of work

| Step | Where | What |
|---|---|---|
| 1 | all | This file and the README pointers. Tag Incident-Agent `v1-frozen` |
| 2 | Observability-Agent | New repo. Port the v1 responder. Add durable state, then memory, triggers, cleanup. Runs against Core1 v1 until the v2 contract is ready |
| 3 | Incident-Agent | Remove the responder. Port `scenarios.json`, the scenario driver and the eval harness into a scenario runner and scorer |
| 4 | Core1 v2 | Phase 7 delivers fault primitives and the injection endpoint only (`DESIGN.md` section 10) |
| 5 | both agents | Move to the v2 contract after Core1 phase 8. Traces need phase 3, ITSM and paging need phase 4 |

## Open questions

- Durable state for Observability-Agent: SQLite on the host, or Postgres (CNPG) in mgmt. Host first is simpler while
  the lab is not always up.
- Where Observability-Agent runs when "always on": a supervised host process (launchd) or a Deployment in mgmt.
- Sandbox definition: confirm the list (fix branches, draft PRs, scratch namespaces for dry runs, SDK workspaces) and
  a TTL for each.

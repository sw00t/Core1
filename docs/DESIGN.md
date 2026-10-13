# Core1 design notes

## Boundary
The base is everything an enterprise would already have: the cluster, the services, the telemetry, the
change process. It deliberately contains no agent code. The agent layer consumes the base through
Prometheus, Loki, Alertmanager webhooks, the Kubernetes API (read-only) and git. A different agent,
SDK or model reuses the base unchanged.

## Choices and why
- k3d, one node: fastest and lightest local Kubernetes that still runs real images and real
  Helm charts. Node count is a setting for later multi-node work.
- kube-prometheus-stack via Helm: the operator stack is too large to hand-write and is what most
  enterprises run. Values stay near defaults; k3s-internal components are disabled to avoid false alerts.
- Loki and Alloy as plain manifests, not charts: ~150 lines total that can be read in one sitting,
  versus chart defaults that assume a production footprint (caches, canaries, gateways).
- Alloy over Promtail: Promtail reached end of life in 2026; Alloy is Grafana's supported collector.
- Config repo plus deploy.sh: changes to the running system are commits, deploys are explicit, and
  each deploy is recorded three ways (git log, rollout history change-cause, Loki deploy-events).
- Secrets outside the config repo: the agent's identity cannot read secrets and the repo holds none.
- Scenario commits look ordinary: messages and authors read like real change history. The answer files
  live in Core1, not in the config repo the agent sees.
- Short alert windows (1m) and scrape interval (15s): fast feedback in a lab; not production values.
- Disk ceiling enforced in code, not by convention.

## Memory and disk (estimates, measured on first run)
k3s ~1 GB, Prometheus stack ~1.5 GB, Loki+Alloy ~0.5 GB, Postgres ~0.2 GB, services and load ~0.6 GB.
Images on disk: k3s, Prometheus stack, Loki, Alloy, Postgres, Python base: roughly 3 to 5 GB.

## Done means
`make down && make up && make verify` passes twice in a row on the target machine.

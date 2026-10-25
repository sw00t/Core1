# Sizing

Phase 0 spike: three empty k3d clusters, measured idle. 2026-10-15, 21:44 to 22:01 local time.

## Result

| Measure | Value |
|---|---|
| VM memory used, three idle clusters | 3038 MiB mean, 3210 MiB max |
| VM memory used before any cluster | 782 MiB |
| Cost of three empty clusters | about 2.2 GiB (2173 MiB mean by container, 2256 MiB by VM delta) |
| VM memory left for L1 to L3 | about 21 GiB of 24246 MiB |
| Swap used | 0 |
| Idle CPU, all k3d containers | 0.29 cores mean, 0.37 max |
| Docker disk (images, volumes, containers) | 1.28 GB |
| `Docker.raw` allocated on macOS | 11 MB before, 1.42 GB after |
| Create time per cluster | 25 to 26 s (mgmt 25, stage 26, prod 25) |

Three empty clusters use about 9 percent of the VM. Memory is not the constraint at this layer.

## Setup

| Item | Value |
|---|---|
| Host | M3 Pro, 36 GB, macOS 26.6.2 |
| Docker Desktop | 4.95.0, engine 29.8.2. VM: 8 CPU, 24832 MiB, 1 GiB swap, 496 GiB disk (`docs/host.md`) |
| k3d | v5.9.0 (v1 pin, provisional) |
| k3s | `rancher/k3s:v1.36.5-k3s1` (v1 pin, provisional) |
| Clusters | `core1-mgmt`, `core1-stage`, `core1-prod` |
| Shape | 1 server, 1 agent, plus the k3d load balancer and tools containers |
| Disabled | Traefik, servicelb (v2 brings its own Gateway API controller) |
| Kept | CoreDNS, metrics-server, local-path-provisioner |
| API | `127.0.0.1:16550`, `16551`, `16552`. No other host ports |
| Docker access | `DOCKER_HOST=unix://$HOME/.docker/run/docker.sock` (default socket setting is off) |

## Method

1. Baseline before any cluster: `/proc/meminfo` in the VM (via a throwaway k3s container), `docker system df`,
   allocated size of `Docker.raw`.
2. Create the clusters one at a time with `k3d cluster create ... --wait`. Wall-clock time per create.
3. Wait for every kube-system pod Ready. Settle 5 minutes.
4. Sample every 30 s for 10 minutes (20 samples): `docker stats` per container, VM `/proc/meminfo`,
   `kubectl top nodes` per cluster.
5. Disk after the idle period: `docker system df -v`, volume mounts per node, `Docker.raw` allocated size.

VM memory used is `MemTotal - MemAvailable`, so reclaimable page cache is not counted.

## Memory detail

Per cluster, sum of its containers (`docker stats`, MiB):

| Cluster | Mean | Max |
|---|---|---|
| mgmt | 695 | 703 |
| stage | 760 | 768 |
| prod | 718 | 726 |
| All | 2173 | 2194 |

Per container role, across the three clusters (MiB):

| Role | Mean | Max |
|---|---|---|
| server-0 (k3s control plane, plus all system pods) | 603 | 644 |
| agent-0 (empty worker) | 98 | 101 |
| serverlb (k3d nginx proxy) | 17 | 18 |
| tools (k3d helper, stays running) | 5 | 5 |

`kubectl top nodes`: servers 574 to 637 MiB and 84 to 86 millicores, agents 98 MiB and 17 millicores.
All system pods land on the server node; the agents hold none until workloads arrive.

## Disk detail

| Item | Size |
|---|---|
| Images: `rancher/k3s` 331 MB, `k3d-proxy` 105 MB, `k3d-tools` 37 MB | 473 MB |
| Volumes: `/var/lib/rancher/k3s` on each server | about 267 MB each, 800 MB total |
| Volumes: agents, logs, kubelet, CNI, image import | under 1 MB in total |
| Container writable layers | 2 MB |

Disk is not a constraint. The 496 GiB disk image and the 600 GB budget leave room for images of every L1 component.

## What did not work

The macOS-side reading of the VM process was not usable. `footprint` reported 1637 MB both before and after the
clusters, and RSS fell from 2.9 GB to 0.96 GB while the guest used more. Apple's Virtualization framework does not
expose guest memory that way. The in-VM `/proc/meminfo` figure is the one to trust. The sampler also failed to parse
`footprint` output; this does not affect the numbers above.

## Implications for the full profile

The rest is an estimate, not a measurement. Phase 3 measures it.

- 21 GiB is left for L1 to L3 after the empty clusters.
- Planning ranges for the full profile, from typical idle footprints with lab-sized limits:
  mgmt components (Argo CD, Keycloak, OpenBao, ESO, Prometheus receiver, Alertmanager, Loki, Tempo, Grafana,
  mocks, registry, traffic generator, fault endpoint) about 4.5 to 6 GiB. Each workload cluster (CNPG, Redpanda,
  Valkey, Kyverno, cert-manager, Gateway API, Prometheus agent, OTel Collector, Alloy, ten app services) about 4 to
  5 GiB. Total about 15 to 18 GiB including the clusters.
- On these estimates the full profile fits in 24 GiB with a few GiB to spare. The largest uncertainties are Redpanda
  (needs explicit memory flags to stay near 1 GiB), Keycloak (JVM), and Kyverno.
- If phase 3 measures over budget, the trim order in `DESIGN.md` section 11 applies. One more lever measured here:
  an agent node costs about 100 MiB idle per cluster, so dropping agents saves little. Keep the 1 server plus
  1 agent shape unless it causes trouble.

## Raw data

Samples and logs stayed in the Claude Code session scratchpad (not committed): `stats.jsonl`, `meminfo.txt`,
`top-nodes.txt`, `create-*.log`, `disk-df*.txt`. The figures above are the full summary.

## Phase 2 measurement (platform core, no app yet)

2026-10-16, working copy, all 22 platform apps synced and healthy, idle, six samples 10 s apart.

| Measure | Value |
|---|---|
| VM memory used | 14329 MiB mean, 14474 MiB max, of 24246 MiB |
| mgmt (containers) | 5960 MiB |
| stage (containers) | 4991 MiB |
| prod (containers) | 5197 MiB |
| registry | 48 MiB |

Largest consumers:

| Where | What | Memory |
|---|---|---|
| each server node | k3s itself (API server, datastore) | about 2.5 to 2.8 GiB above its pods |
| mgmt | Argo CD application controller | 1417 MiB (limit raised to 2 GiB after an OOM kill at 768 MiB) |
| mgmt | Keycloak | 575 MiB |
| stage, prod | Kafka (one KRaft node) | 536 MiB |
| stage, prod | Strimzi operator | 244 MiB |

The k3s server cost grows with the number of CRDs (Kyverno, Strimzi, External Secrets, Envoy Gateway, cert-manager
together install well over a hundred). This is the main gap against the phase 0 estimate, which assumed 4 to 5 GiB
per workload cluster including the app.

Projection (estimate): the reference app (phase 5) adds about 1 GiB per workload cluster; observability (phase 3)
adds about 2 to 3 GiB in mgmt and a few hundred MiB per workload cluster. That lands at about 20 to 22 GiB of
24 GiB. It fits, with little headroom. Levers before the DESIGN.md trim order: turn off Kyverno's reports and
background controllers, lower Kafka's heap, drop the agent nodes (about 100 MiB each), or raise the Docker VM above
24 GiB (the host has 36 GB). Measure again at the end of phase 3.

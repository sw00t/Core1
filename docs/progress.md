# Progress

## 2026-10-15: Phase 0, prep and spike

### Done

- Tagged `main` (`b35f275`) as `v1-frozen`, annotated, and pushed it to `sw00t/Core1`. Core1-agent can pin it.
- Created branch `v2` from `main`. Repo-local git identity: `Core1 build <core1-build@users.noreply.github.com>`.
- Inventoried v1: `docs/v1-inventory.md`. Every file and Make target marked keep, rewrite, or delete, with the phase
  that handles it and the telco content that moves to `packs/telco/`.
- Deleted the files marked "delete now": `docs/DESIGN.md` (v1), `docs/RUNNER.md`, `docs/TRACING.md`,
  `scripts/runner.sh`, `reports/verify-*.md`. Removed the `runner` Make target and links to the deleted docs.
  Added a v2 banner to `README.md`.
- Recorded Docker Desktop settings: `docs/host.md`. S set 8 CPU, 24832 MiB, 496 GiB disk. Claude Code changed no
  settings.
- Sizing spike: `docs/sizing.md`. Three empty k3d clusters (1 server, 1 agent each) use about 2.2 GiB idle, leaving
  about 21 GiB of the 24 GiB VM. Docker disk 1.28 GB. Create time 25 to 26 s per cluster.
- Deleted the spike clusters. No k3d containers, volumes, or networks remain. The k3s, k3d-proxy and k3d-tools
  images stay cached (473 MB). `.bin` holds k3d v5.9.0, kubectl v1.36.5, helm v4.3.0 (git-ignored).
- Started `docs/backlog.md`.

### Findings

- k3d works with `DOCKER_HOST=unix://$HOME/.docker/run/docker.sock`. The default Docker socket setting can stay off.
- GitHub rulesets on the private `sw00t/Core1` return 403 "Upgrade to GitHub Pro". Branch protection on a private
  `core1-gitops` needs Pro or a public repo.
- Host Python: `python3` on PATH is a broken pyenv shim. `/usr/bin/python3` is 3.9.6. Homebrew has 3.11.
  `uv` is installed. The phase 1 CLI needs a decided Python setup.
- k3d leaves a `k3d-<cluster>-tools` container running per cluster (5 MiB each).
- The macOS-side VM memory reading is not usable with Apple's Virtualization framework. Measure inside the VM.

### Next

Phase 1 (host and CLI), after S approves phase 0 and the phase 1 plan.

### Decisions from S for phase 1 and 2

1. Cluster names: `mgmt`, `stage`, `prod`. No prefix.
2. Python for the `core1` CLI: Homebrew Python 3.11.
3. Local OCI registry: k3d-managed. Phase 1 verifies its image like any other component.
4. Docker access: the CLI sets `DOCKER_HOST` itself. The default socket setting stays off.
5. Host ports: one block per cluster, all on `127.0.0.1`. Nothing listened in 16000 to 18999 on 2026-10-15.

   | Block | API | HTTP gateway | HTTPS gateway | Reserved |
   |---|---|---|---|---|
   | registry | | | | `17000` |
   | mgmt | `17143` | `17180` | `17181` | rest of 17100 to 17199 |
   | stage | `17243` | `17280` | `17281` | rest of 17200 to 17299 |
   | prod | `17343` | `17380` | `17381` | rest of 17300 to 17399 |

6. Cluster shape: 1 server plus 1 agent per cluster.
7. GitOps repo: `sw00t/core1-gitops`. It exists, private, default branch `main`. Without GitHub Pro it gets no
   rulesets or branch protection, so CI can fail a PR but cannot block its merge. Phase 2 plan addresses this.

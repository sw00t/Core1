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

### Open questions for S before phase 1

1. Cluster names: `mgmt`, `stage`, `prod` as in `DESIGN.md`, or prefixed `core1-mgmt` and so on (used in the spike
   to avoid clashes with other k3d clusters)?
2. Python setup for the `core1` CLI: `uv` managing a pinned Python and a project venv, or Homebrew Python 3.11?
3. Local OCI registry: k3d-managed registry or a separately run one. Phase 1 verifies the candidate.
4. Docker access: CLI sets `DOCKER_HOST` itself (spike result), or S enables the default socket?
5. Host port scheme for three clusters (API ports and gateway entry points), for example one block per cluster.
6. Cluster shape: keep 1 server plus 1 agent per cluster in the full profile?
7. Before phase 2: GitOps repo owner and name (proposed `sw00t/core1-gitops`), and visibility given the Pro finding.

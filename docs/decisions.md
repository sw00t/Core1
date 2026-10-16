# Decisions

Component verification and design choices. Each pinned component is checked for maintenance status, licence, and an
arm64 build before it enters `versions.env`. Newest entries at the bottom.

## 2026-10-15: Phase 1 host tools and CLI

Checked against GitHub releases, PyPI, and image manifests.

| Component | Pin | Licence | Maintenance | arm64 | Notes |
|---|---|---|---|---|---|
| k3d | v5.9.0 | MIT | Latest stable, released 2026-06-02. Repo active | darwin-arm64 binary | |
| k3d-proxy, k3d-tools | 5.9.0 | MIT | Ship with k3d | linux/arm64 images | Pinned via `K3D_IMAGE_LOADBALANCER` and `K3D_IMAGE_TOOLS` |
| k3s | v1.36.5+k3s1 | Apache-2.0 | Released 2026-09-30 | linux/arm64, ran in the phase 0 spike | One minor behind latest (v1.37.1, first patch). n-1 with the latest patch is the steadier base |
| kubectl | v1.36.5 | Apache-2.0 | `stable-1.36.txt` | darwin-arm64 | Matches k3s |
| helm | v4.3.1 | Apache-2.0 | Released 2026-10-15. Repo active | darwin-arm64 | Not used until phase 2. Re-check then |
| Registry | `registry:3.1.2` | Apache-2.0 | distribution v3.1.2, 2026-09-24 | arm64 in the manifest list | k3d's default is `registry:2`; that line's last release is v2.8.3 (2023). Pinned through `k3d registry create --image` |
| Python | 3.11 (Homebrew 3.11.17) | PSF | Security fixes until 2027-10 | Native | S's choice. Typer needs 3.10 or newer |
| typer | 0.27.3 | MIT | Released 2026-10-06 | Pure Python | |
| rich | 15.0.0 | MIT | Released 2026-04-12 | Pure Python | Typer dependency |
| shellingham | 1.5.4 | ISC | Stable, small | Pure Python | Typer dependency |
| annotated-doc | 0.0.5 | MIT | Typer dependency | Pure Python | |
| markdown-it-py | 4.2.0 | MIT | Rich dependency | Pure Python | |
| mdurl | 0.1.2 | MIT | markdown-it-py dependency | Pure Python | |
| Pygments | 2.21.0 | BSD-2-Clause | Rich dependency | Pure Python | |
| pytest (dev only) | 9.1.1 | MIT | Released 2026-06-19 | Pure Python | With iniconfig 2.3.1 (MIT), packaging 26.3 (Apache-2.0 or BSD-2-Clause), pluggy 1.6.0 (MIT; 1.7.0 was one day old) |

## 2026-10-15: Phase 1 design choices

- Kubernetes and Docker access are subprocess calls to the pinned `kubectl`, `k3d`, and `docker`. No Python
  Kubernetes client. Fewer dependencies, same commands a human would run.
- All three clusters and the registry share one Docker network, `core1`. mgmt reaches the stage and prod API servers
  (phase 2) and receives remote-write (phase 3) without going through the host.
- Traefik is disabled. servicelb stays enabled so a Gateway API LoadBalancer Service gets node ports 80 and 443,
  which the k3d load balancer maps to the host gateway ports.
- Host ports bind to `127.0.0.1` only. Blocks: registry 17000, mgmt 171xx, stage 172xx, prod 173xx
  (API x43, HTTP x80, HTTPS x81). `CORE1_PORT_BASE` moves all of them.
- The CLI sets `DOCKER_HOST=unix://$HOME/.docker/run/docker.sock` when it is unset. The Docker Desktop default socket
  setting stays off.
- `core1 nuke` removes runtime state. `core1 nuke --all` also removes `.bin`, `.venv`, and the images Core1 pulled.

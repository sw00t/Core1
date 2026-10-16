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
- Traefik is disabled. servicelb stays enabled so a Gateway API LoadBalancer Service gets node ports, which the k3d
  load balancer maps to the host gateway ports. (Phase 2 changed the mapping to the same port number inside and
  outside; see below.)
- Host ports bind to `127.0.0.1` only. Blocks: registry 17000, mgmt 171xx, stage 172xx, prod 173xx
  (API x43, HTTP x80, HTTPS x81). `CORE1_PORT_BASE` moves all of them.
- The CLI sets `DOCKER_HOST=unix://$HOME/.docker/run/docker.sock` when it is unset. The Docker Desktop default socket
  setting stays off.
- `core1 nuke` removes runtime state. `core1 nuke --all` also removes `.bin`, `.venv`, and the images Core1 pulled.

## 2026-10-16: Phase 2 platform components

Rule: the newest minor whose .0 is at least four weeks old, at its latest patch. Licences from the GitHub repos;
arm64 from each image's manifest list. Charts are rendered by kustomize (`helmCharts`), the same way in Argo CD and
in CI.

| Component | Pin | Licence | Maintenance | arm64 | Notes |
|---|---|---|---|---|---|
| Argo CD | v3.5.5 (chart 10.10.5) | Apache-2.0 | 3.5.0 on 2026-08-04, 3.5.5 on 2026-10-12 | yes | Dex off; OIDC straight to Keycloak |
| Redis (Argo CD cache) | 8.6.4-alpine (chart default) | AGPLv3 / RSALv2 / SSPLv1, choice of one | Active | yes | Internal use under AGPLv3 is fine. Valkey is a drop-in option if this ever matters |
| Keycloak | 26.7.5 | Apache-2.0 | 26.8.0 is two weeks old | yes | Plain manifests; realm re-imported from git on every start |
| OpenBao | 2.6.4 (chart 0.29.6) | MPL-2.0 | 2.7.0 is three weeks old | yes | Standalone, raft storage, initialised and unsealed by `core1 up` |
| External Secrets | v2.11.0 (chart 2.11.0) | Apache-2.0 | 2.11.0 on 2026-09-18; 2.12 and 2.13 too new | yes | |
| cert-manager | v1.21.2 | Apache-2.0 | 1.21.0 on 2026-07-08 | yes | |
| Envoy Gateway | v1.9.2 | Apache-2.0 | 1.9.0 on 2026-08-15 | yes | Ships Gateway API CRDs |
| Kyverno | v1.19.1 (chart 3.9.1) | Apache-2.0 | 1.19.0 on 2026-08-20 | yes | stage and prod; CLI in CI and `.bin` |
| CloudNativePG | 1.30.1 (chart 0.29.1) | Apache-2.0 | 1.30.0 on 2026-06-29 | yes | Postgres image 17.11-minimal-trixie |
| Strimzi | 1.2.0, Kafka 4.3.1 | Apache-2.0 | 1.3.0 is four days old | yes | KRaft, one dual-role node |
| Valkey | 9.1.2 | BSD-3-Clause | 9.1.0 on 2026-05-19 | yes | Plain StatefulSet |
| kustomize, kubeconform | v5.8.3, v0.8.0 | Apache-2.0 | Active | darwin-arm64 binaries | |
| datreeio CRDs-catalog | commit 63669a5 (2026-10-08) | Apache-2.0 | Active | n/a | CRD schemas for kubeconform |

Rejected: **Redpanda** (BSL 1.1, source-available; it would allow this use, but S chose Apache Kafka).

## 2026-10-16: Phase 2 design choices

- **One URL inside and outside.** `*.<cluster>.localhost` resolves to 127.0.0.1 in browsers and, through a
  CoreDNS rewrite, to `k3d-<cluster>-serverlb` in pods. Gateway listeners use the host port numbers, so OIDC
  issuer URLs match everywhere.
- **Lab CA.** Created once by `core1 up` in `.ca/`, copied into each cluster's cert-manager namespace at bootstrap.
  Not delivered through External Secrets: stage and prod need it to trust OpenBao in the first place.
- **GitOps seeding.** Core1 owns fixed paths in `core1-gitops`; `up` opens a PR when its template differs, waits
  for CI, and squash-merges. Other paths (apps, packs) are never touched.
- **Argo CD settings.** 30 s polling; `reposerver.parallelism.limit: 1` (apps for several clusters share a base
  folder and parallel chart pulls collide); server-side diff on, plus Gateway API defaults written out in the
  manifests, so defaulted fields are not reported as drift.
- **Secrets.** OpenBao in mgmt; one Kubernetes auth mount per cluster; stage and prod are reviewed with the
  client's own token (External Secrets has auth-delegator), so no long-lived reviewer token exists. Tokens from
  OpenBao live 15 minutes. GitHub tokens are written from `.env` on every `up`, so a rotated token reaches the
  cluster. Lab trade-offs: the unseal key and root token sit in `.work/openbao/init.json`; Argo CD's cluster
  credentials for stage and prod are long-lived ServiceAccount tokens created at bootstrap.
- **Identity.** Keycloak realm `core1` with groups `core1-admins` and `core1-viewers`. Argo CD maps them to admin and
  read-only; nobody else gets a role.
- **Policy.** One ClusterPolicy (`core1-baseline`), enforced in every namespace except the platform's own. The same
  file runs in CI with `kyverno apply` against each rendered folder, plus `kyverno test` cases. Namespace exclusion
  by name (not label) because the CLI in CI cannot see namespace labels.
- **CI skips.** kubeconform skips CRD definitions and `external-secrets.io/v1` store kinds (the catalog schema does
  not compile); External Secrets' webhook validates those in the cluster.
- **Data services.** Kafka uses a plain internal listener without auth (lab trade-off). Postgres credentials are
  generated by CloudNativePG; the Valkey password by `core1 up` into OpenBao.

# Host

Target host and Docker Desktop settings for Core1 v2. Recorded in phase 0 (2026-10-15).

## Machine

| Item | Value |
|---|---|
| Model | Apple M3 Pro, 12 cores, 36 GB RAM |
| OS | macOS 26.6.2 (build 25G83) |
| Free disk on the data volume | 820 GiB of 926 GiB |
| Docker Desktop | 4.95.0, engine 29.8.2, kernel 7.0.14-linuxkit, arm64 |

## Docker Desktop settings

S applied the resource values during phase 0. Claude Code read the rest and changed nothing.
Source: `docker info` and `~/Library/Group Containers/group.com.docker/settings-store.json`.
Settings missing from that file are at their Docker Desktop defaults.

| Setting | Current | Recommended | Notes |
|---|---|---|---|
| Memory | 24832 MiB | Keep | About 24 GB for the VM, 12 GB left for macOS |
| CPUs | 8 of 12 | Keep | |
| Swap | 1 GiB | Keep | Read from `/proc/meminfo` in the VM |
| Disk image size | 507904 MiB (496 GiB) | Keep | Inside the 600 GB budget. `Docker.raw` is sparse |
| Virtual machine manager | Default | Apple Virtualization framework | |
| File sharing | Default | VirtioFS | |
| Rosetta for x86/amd64 | On (LinuxRosetta process running) | Keep | v2 still verifies every image has an arm64 build. Rosetta only hides misses |
| Containerd image store | On | Keep | v2 pushes images to a local registry, which avoids the v1 `k3d image import` digest bug |
| Allow the default Docker socket | Off | Keep off | k3d works with `DOCKER_HOST` set (see below) |
| Built-in Kubernetes | Off | Must stay off | Core1 uses k3d |
| Resource Saver | Default | Keep | Running clusters keep the VM awake |
| Start at login | Off | S's choice | |

## Docker socket

With the default socket off, `/var/run/docker.sock` does not exist on the host. Docker Desktop serves the engine at
`~/.docker/run/docker.sock` (context `desktop-linux`). In the phase 0 spike, k3d v5.9.0 created three clusters with:

```
export DOCKER_HOST=unix://$HOME/.docker/run/docker.sock
```

No errors or warnings. The k3d tools container and the `host.k3d.internal` CoreDNS injection worked. Since phase 1
the `core1` CLI sets `DOCKER_HOST` itself when it is unset, so the setting stays off. To run `docker` or `k3d` by
hand against Core1, export the line above first.

## Troubleshooting

Carried from v1 `docs/TROUBLESHOOTING.md` where it still applies.

**A tool download fails (for example a `dl.k8s.io` TLS error, or `cdn.dl.k8s.io` does not resolve).** Some home
routers and DNS filters block the k8s.io download CDN. Install the tool another way and point Core1 at it in `.env`:

```
brew install kubectl
echo 'KUBECTL_BIN=/opt/homebrew/bin/kubectl' >> .env
```

`K3D_BIN` and `HELM_BIN` work the same way. The binary is copied into `.bin`. Nothing else changes.

**A pod is stuck in ImagePullBackOff on `registry.k8s.io`.** Same cause, seen from the cluster node. v1 pulled such
images on the host and imported them into the cluster (`prepull_via_host` in `scripts/obs-install.sh`). If the host
cannot pull either, the network is the problem.

**`k3d image import` fails with "content digest ... not found".** The containerd image store saves multi-arch images
in a way k3d cannot import. v2 pushes to the local registry instead. If an import is ever needed, save a
single-platform tar first (`docker save --platform linux/arm64`).

**"Permission denied" running `./core1` or a script.** Some editors and sync tools drop the executable bit or write
0600 files. `chmod +x core1`. Git stores the bit, so a fresh clone is fine.

**A port is already in use.** `./core1 doctor` names it. Set `CORE1_PORT_BASE` in `.env` (see `.env.example`), then
`./core1 nuke` and `./core1 up`. Host ports bind to 127.0.0.1 only.

**Everything is slow or pods are evicted.** Docker Desktop memory is too low. See the settings table above.

## Licence note

Docker Desktop needs a paid subscription for larger commercial organisations. Personal and small-business use is
free. OrbStack or Colima are the fallback (`DESIGN.md` section 11).

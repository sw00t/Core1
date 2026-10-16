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

No errors or warnings. The k3d tools container and the `host.k3d.internal` CoreDNS injection worked. The phase 1 CLI
should set `DOCKER_HOST` itself so the setting can stay off.

## Host tips carried from v1

- Some networks block the `dl.k8s.io` and `registry.k8s.io` CDNs. v1 worked around this with `KUBECTL_BIN` overrides
  and by pulling blocked images on the host. Not seen in phase 0: all downloads and pulls succeeded.
- Some sync tools drop executable bits or write 0600 files. v1 forces modes in the Dockerfile and in git.

## Licence note

Docker Desktop needs a paid subscription for larger commercial organisations. Personal and small-business use is
free. OrbStack or Colima are the fallback (`DESIGN.md` section 11).

"""Remove what Core1 created. Default: runtime state. --all: also tools, venv and pulled images."""
import shutil

from . import docker
from .clusters import cluster_states, k3d
from .config import NETWORK, REGISTRY_CONTAINER
from .shell import log


def core1_images(settings):
    return [settings.version(k) for k in ("K3S_IMAGE", "K3D_PROXY_IMAGE", "K3D_TOOLS_IMAGE", "REGISTRY_IMAGE")]


def _core1_volumes(settings):
    """Volumes k3d made for Core1's clusters: named k3d-<cluster>-* or labelled k3d.cluster=<cluster>."""
    found = set()
    for c in settings.clusters:
        found.update(v for v in docker.lines(settings, "volume", "ls", "--format", "{{.Name}}") if v.startswith(f"k3d-{c.name}-"))
        found.update(docker.lines(settings, "volume", "ls", "-q", "--filter", f"label=k3d.cluster={c.name}"))
    return sorted(found)


def nuke(settings, everything=False):
    names = [c.name for c in settings.clusters]
    if settings.tool("k3d").exists():
        present = [n for n in names if n in cluster_states(settings)]
        for n in present:
            log(f"deleting cluster {n}")
            k3d(settings, "cluster", "delete", n)
        if docker.container_exists(settings, REGISTRY_CONTAINER):
            log(f"deleting registry {REGISTRY_CONTAINER}")
            k3d(settings, "registry", "delete", REGISTRY_CONTAINER)
    else:
        # no k3d binary (for example after nuke --all): remove Core1's containers and volumes by name and label
        for n in docker.lines(settings, "ps", "-a", "--format", "{{.Names}}"):
            if n == REGISTRY_CONTAINER or any(n.startswith(f"k3d-{c}-") for c in names):
                log(f"removing container {n}")
                docker.docker(settings, "rm", "-fv", n)
        for v in _core1_volumes(settings):
            docker.docker(settings, "volume", "rm", "-f", v, check=False)
    if docker.network_exists(settings, NETWORK):
        log(f"deleting docker network {NETWORK}")
        docker.docker(settings, "network", "rm", NETWORK, check=False)

    for c in settings.clusters:
        c.kubeconfig(settings).unlink(missing_ok=True)
    if settings.kube_dir.exists() and not any(settings.kube_dir.iterdir()):
        settings.kube_dir.rmdir()
    shutil.rmtree(settings.work_dir, ignore_errors=True)

    if everything:
        for ref in core1_images(settings):
            if docker.image_present(settings, ref):
                log(f"removing image {ref}")
                docker.docker(settings, "rmi", ref, check=False)
        for d in cache_dirs(settings):
            if d.exists():
                log(f"removing {d.relative_to(settings.root)}")
                shutil.rmtree(d, ignore_errors=True)
    return leftovers(settings, everything)


def cache_dirs(settings):
    """Kept by plain nuke, removed by nuke --all. .ca survives plain nuke so a CA trusted in macOS stays valid."""
    return (settings.bin_dir, settings.venv_dir, settings.root / ".ca")


def leftovers(settings, everything=False):
    """Anything Core1 created that still exists."""
    names = [c.name for c in settings.clusters]
    left = []
    for n in docker.lines(settings, "ps", "-a", "--format", "{{.Names}}"):
        if n == REGISTRY_CONTAINER or any(n.startswith(f"k3d-{c}-") for c in names):
            left.append(f"container {n}")
    left += [f"volume {v}" for v in _core1_volumes(settings)]
    if docker.network_exists(settings, NETWORK):
        left.append(f"network {NETWORK}")
    for c in settings.clusters:
        if c.kubeconfig(settings).exists():
            left.append(f"file {c.kubeconfig(settings).relative_to(settings.root)}")
    if settings.work_dir.exists():
        left.append(f"dir {settings.work_dir.relative_to(settings.root)}")
    if everything:
        left += [f"image {r}" for r in core1_images(settings) if docker.image_present(settings, r)]
        left += [f"dir {d.relative_to(settings.root)}" for d in cache_dirs(settings) if d.exists()]
    return sorted(set(left))

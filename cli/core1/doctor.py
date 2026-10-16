"""Host checks: platform, Docker Desktop resources, ports, tools."""
import json
import platform
import shutil
import socket
import sys
from pathlib import Path

from . import docker
from .clusters import cluster_states
from .config import REGISTRY_CONTAINER
from .tools import tool_version_report

GIB = 1024 ** 3
MIN_VM_MEMORY_GIB = 23
MIN_CPUS = 8
MIN_FREE_DISK_GB = 50
DOCKER_SETTINGS = Path.home() / "Library" / "Group Containers" / "group.com.docker" / "settings-store.json"


class Report:
    def __init__(self):
        self.failed = False

    def ok(self, msg):
        print(f"  ok    {msg}")

    def note(self, msg):
        print(f"  note  {msg}")

    def warn(self, msg):
        print(f"  warn  {msg}")

    def fail(self, msg):
        print(f"  FAIL  {msg}")
        self.failed = True


def port_free(port):
    s = socket.socket()
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        s.bind(("127.0.0.1", port))
        return True
    except OSError:
        return False
    finally:
        s.close()


def port_owner(settings, port, states):
    """Which Core1 component should hold PORT, if that component exists."""
    if port == settings.registry_port:
        return REGISTRY_CONTAINER if docker.container_exists(settings, REGISTRY_CONTAINER) else None
    for c in settings.clusters:
        if port in (c.api_port, c.http_port, c.https_port):
            return f"cluster {c.name}" if c.name in states else None
    return None


def run_doctor(settings):
    r = Report()
    os_name, arch = platform.system(), platform.machine()
    if os_name == "Darwin" and arch == "arm64":
        r.ok(f"host macOS {platform.mac_ver()[0]} arm64")
    else:
        r.warn(f"host {os_name}/{arch}; Core1 targets macOS on Apple Silicon")

    v = sys.version_info
    if (v.major, v.minor) == (3, 11):
        r.ok(f"python {platform.python_version()} ({sys.executable})")
    else:
        r.fail(f"python 3.11 required, running {platform.python_version()}")
    for t in ("git", "curl"):
        (r.ok if shutil.which(t) else r.fail)(f"{t}: {shutil.which(t) or 'not found'}")

    info = docker.info(settings)
    if info is None:
        r.fail("docker engine not reachable (is Docker Desktop running?)")
    else:
        mem = info.get("MemTotal", 0) / GIB
        cpus = info.get("NCPU", 0)
        r.ok(f"docker {info.get('ServerVersion')} on {info.get('OperatingSystem')}: {cpus} cpus, {mem:.1f} GiB")
        if mem < MIN_VM_MEMORY_GIB:
            r.warn(f"docker VM has {mem:.1f} GiB; the full profile wants about 24 GiB (docs/host.md)")
        if cpus < MIN_CPUS:
            r.warn(f"docker VM has {cpus} cpus; {MIN_CPUS} recommended")
    if DOCKER_SETTINGS.exists():
        try:
            if json.loads(DOCKER_SETTINGS.read_text()).get("KubernetesEnabled"):
                r.fail("Docker Desktop built-in Kubernetes is on; turn it off (Core1 uses k3d)")
            else:
                r.ok("Docker Desktop built-in Kubernetes is off")
        except (json.JSONDecodeError, OSError):
            r.note("could not read Docker Desktop settings")

    free_gb = shutil.disk_usage(settings.root).free / 1e9
    (r.ok if free_gb >= MIN_FREE_DISK_GB else r.warn)(f"host free disk {free_gb:.0f} GB (want {MIN_FREE_DISK_GB}+)")

    states = cluster_states(settings) if (settings.tool("k3d").exists() and info is not None) else {}
    for port in settings.all_ports():
        if port_free(port):
            continue
        owner = port_owner(settings, port, states)
        if owner:
            r.note(f"port {port} held by {owner} (expected)")
        else:
            r.fail(f"port 127.0.0.1:{port} in use by something else; change CORE1_PORT_BASE in .env")
    r.ok(f"ports checked: registry {settings.registry_port}, clusters "
         + ", ".join(f"{c.name} {c.api_port}/{c.http_port}/{c.https_port}" for c in settings.clusters))

    for name, want, have in tool_version_report(settings):
        if have == want:
            r.ok(f"{name} {have}")
        else:
            r.note(f"{name} {want} not in .bin yet (up downloads it)" if have is None else f"{name} {have} in .bin, {want} pinned (up replaces it)")

    check_tokens(settings, r)
    return not r.failed


def core1_repo(settings):
    """owner/name of Core1's own GitHub remote, if any."""
    from .shell import run
    url = run(["git", "-C", settings.root, "remote", "get-url", "origin"], check=False).stdout.strip()
    if "github.com" not in url:
        return None
    return url.split("github.com", 1)[1].lstrip(":/").removesuffix(".git")


def check_tokens(settings, r, now=None):
    from datetime import datetime, timezone
    from .github import GitHub, GitHubError

    own = core1_repo(settings)
    for which in ("argocd", "automation"):
        key = f"CORE1_GITHUB_TOKEN_{which.upper()}"
        token = settings.token(which)
        if not token:
            r.fail(f"{key} missing (.env); see .env.example")
            continue
        try:
            gh = GitHub(token, settings.gitops_repo)
            status, expiry = gh.token_expiry()
            if status != 200:
                r.fail(f"{key} cannot read {settings.gitops_repo} (HTTP {status})")
                continue
            msg = f"{key} reads {settings.gitops_repo}"
            if expiry:
                when = datetime.strptime(expiry.replace(" UTC", ""), "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
                days = (when - (now or datetime.now(timezone.utc))).total_seconds() / 86400
                if days < 0:
                    r.fail(f"{key} expired on {expiry}")
                    continue
                msg += f", expires in {days:.0f} days"
                (r.warn if days < 7 else r.ok)(msg)
            else:
                r.ok(msg)
            if own and gh.can_read_repo(own):
                r.warn(f"{key} can also read {own}; it only needs {settings.gitops_repo}")
        except GitHubError as e:
            r.warn(f"{key}: could not reach GitHub ({e})")

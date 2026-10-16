"""Network, registry and the three k3d clusters: create, start, delete, kubeconfigs, green checks."""
import json
import time
import urllib.error
import urllib.request

from . import docker
from .config import NETWORK, REGISTRY_CONTAINER, REGISTRY_INTERNAL_PORT, REGISTRY_NAME
from .shell import CommandError, docker_env, log, run

EXPECTED_NODES = 2  # 1 server + 1 agent


def k3d(settings, *args, check=True, timeout=600):
    return run([settings.tool("k3d"), *args], env=docker_env(settings), check=check, timeout=timeout)


def kubectl(settings, cluster, *args, check=True, timeout=60):
    return run([settings.tool("kubectl"), "--kubeconfig", cluster.kubeconfig(settings), *args],
               env=docker_env(settings), check=check, timeout=timeout)


# ---- network and registry ----

def ensure_network(settings):
    if docker.network_exists(settings, NETWORK):
        return
    log(f"creating docker network {NETWORK}")
    docker.docker(settings, "network", "create", "--label", "app.kubernetes.io/part-of=core1", NETWORK)


def ensure_registry(settings):
    if docker.container_exists(settings, REGISTRY_CONTAINER):
        if not docker.container_running(settings, REGISTRY_CONTAINER):
            log(f"starting {REGISTRY_CONTAINER}")
            docker.docker(settings, "start", REGISTRY_CONTAINER)
        return
    log(f"creating registry {REGISTRY_CONTAINER} ({settings.version('REGISTRY_IMAGE')}) on 127.0.0.1:{settings.registry_port}")
    k3d(settings, "registry", "create", REGISTRY_NAME,
        "--image", settings.version("REGISTRY_IMAGE"),
        "--port", f"127.0.0.1:{settings.registry_port}",
        "--default-network", NETWORK)


# ---- clusters ----

def cluster_states(settings):
    """{name: {"servers": (running, total), "agents": (running, total)}} for existing k3d clusters."""
    r = k3d(settings, "cluster", "list", "-o", "json", check=False, timeout=60)
    if r.returncode != 0 or not r.stdout.strip():
        return {}
    states = {}
    for c in json.loads(r.stdout):
        states[c["name"]] = {
            "servers": (c.get("serversRunning", 0), c.get("serversCount", 0)),
            "agents": (c.get("agentsRunning", 0), c.get("agentsCount", 0)),
        }
    return states


def is_running(state):
    return all(running == total and total > 0 for running, total in (state["servers"], state["agents"]))


def create_args(settings, cluster):
    return [
        "cluster", "create", cluster.name,
        "--image", settings.version("K3S_IMAGE"),
        "--servers", "1", "--agents", "1",
        "--network", NETWORK,
        "--registry-use", settings.registry_use,
        "--api-port", f"127.0.0.1:{cluster.api_port}",
        "-p", f"127.0.0.1:{cluster.http_port}:80@loadbalancer",
        "-p", f"127.0.0.1:{cluster.https_port}:443@loadbalancer",
        "--k3s-arg", "--disable=traefik@server:*",
        "--kubeconfig-update-default=false",
        "--kubeconfig-switch-context=false",
        "--wait", "--timeout", "300s",
    ]


def ensure_cluster(settings, cluster, states):
    state = states.get(cluster.name)
    if state is None:
        log(f"creating cluster {cluster.name} (API 127.0.0.1:{cluster.api_port})")
        start = time.monotonic()
        k3d(settings, *create_args(settings, cluster))
        log(f"cluster {cluster.name} created in {time.monotonic() - start:.0f}s")
    elif not is_running(state):
        log(f"starting cluster {cluster.name}")
        k3d(settings, "cluster", "start", cluster.name, "--wait", "--timeout", "300s")
    write_kubeconfig(settings, cluster)


def write_kubeconfig(settings, cluster):
    settings.kube_dir.mkdir(parents=True, exist_ok=True)
    cfg = k3d(settings, "kubeconfig", "get", cluster.name).stdout
    cfg = cfg.replace("https://0.0.0.0:", "https://127.0.0.1:")
    path = cluster.kubeconfig(settings)
    path.write_text(cfg)
    path.chmod(0o600)


# ---- green checks ----

def _http_ok(url, timeout=5):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return 200 <= r.status < 300
    except (urllib.error.URLError, OSError):
        return False


def check_cluster(settings, cluster):
    """[(check, ok, detail)] for one cluster."""
    results = []
    if not cluster.kubeconfig(settings).exists():
        return [(f"{cluster.name}: kubeconfig", False, "missing; run ./core1 up")]

    r = kubectl(settings, cluster, "get", "--raw", "/readyz", check=False, timeout=15)
    results.append((f"{cluster.name}: API 127.0.0.1:{cluster.api_port}", r.returncode == 0 and r.stdout.strip() == "ok",
                    r.stdout.strip() or r.stderr.strip()[:120]))

    r = kubectl(settings, cluster, "get", "nodes", "-o", "json", check=False, timeout=15)
    if r.returncode == 0:
        nodes = json.loads(r.stdout)["items"]
        ready = sum(1 for n in nodes if any(c["type"] == "Ready" and c["status"] == "True" for c in n["status"]["conditions"]))
        results.append((f"{cluster.name}: nodes Ready", ready == EXPECTED_NODES == len(nodes), f"{ready}/{len(nodes)}"))
    else:
        results.append((f"{cluster.name}: nodes Ready", False, r.stderr.strip()[:120]))

    r = kubectl(settings, cluster, "-n", "kube-system", "get", "pods", "-o", "json", check=False, timeout=15)
    if r.returncode == 0:
        pods = json.loads(r.stdout)["items"]
        bad = []
        for p in pods:
            phase = p["status"].get("phase")
            ready = any(c["type"] == "Ready" and c["status"] == "True" for c in p["status"].get("conditions", []))
            if not (phase == "Succeeded" or (phase == "Running" and ready)):
                bad.append(p["metadata"]["name"])
        running = len(pods) - len(bad)
        results.append((f"{cluster.name}: kube-system pods Ready", bool(pods) and not bad,
                        f"{running}/{len(pods)}" + (f"; not ready: {', '.join(bad)}" if bad else "")))
    else:
        results.append((f"{cluster.name}: kube-system pods Ready", False, r.stderr.strip()[:120]))

    url = f"http://{REGISTRY_CONTAINER}:{REGISTRY_INTERNAL_PORT}/v2/"
    r = docker.docker(settings, "exec", cluster.server_container, "wget", "-q", "-O", "/dev/null", url, check=False, timeout=20)
    results.append((f"{cluster.name}: registry from node", r.returncode == 0, url))
    return results


def check_registry(settings):
    url = f"{settings.registry_host_url}/v2/"
    return [("registry from host", _http_ok(url), url)]


def check_all(settings):
    results = check_registry(settings)
    for c in settings.clusters:
        results += check_cluster(settings, c)
    return results


def wait_green(settings, timeout=300):
    """Poll every check until all pass or timeout. Returns the last results."""
    deadline = time.monotonic() + timeout
    while True:
        results = check_all(settings)
        if all(ok for _, ok, _ in results):
            return results
        if time.monotonic() >= deadline:
            return results
        time.sleep(5)


# ---- smoke: pull an image through the registry into every cluster ----

def smoke_pull(settings, timeout=180):
    tools_image = settings.version("K3D_TOOLS_IMAGE")
    push_ref = f"127.0.0.1:{settings.registry_port}/core1/smoke:1"
    pull_ref = f"{settings.registry_use}/core1/smoke:1"
    if not docker.image_present(settings, tools_image):
        docker.docker(settings, "pull", "-q", tools_image, timeout=300)
    docker.docker(settings, "tag", tools_image, push_ref)
    docker.docker(settings, "push", "-q", push_ref, timeout=300)
    docker.docker(settings, "rmi", push_ref, check=False)
    results = []
    for c in settings.clusters:
        kubectl(settings, c, "-n", "default", "delete", "pod", "core1-smoke", "--ignore-not-found", "--wait=true", check=False)
        kubectl(settings, c, "-n", "default", "run", "core1-smoke", f"--image={pull_ref}", "--restart=Never",
                "--labels=app.kubernetes.io/part-of=core1", "--command", "--", "/app/k3d-tools", "noop")
        r = kubectl(settings, c, "-n", "default", "wait", "--for=condition=Ready", "pod/core1-smoke",
                    f"--timeout={timeout}s", check=False, timeout=timeout + 15)
        detail = pull_ref
        if r.returncode != 0:
            d = kubectl(settings, c, "-n", "default", "get", "pod", "core1-smoke",
                        "-o", "jsonpath={.status.containerStatuses[0].state}", check=False)
            detail = f"{pull_ref}: {d.stdout.strip()[:200]}"
        results.append((f"{c.name}: pod pulls from registry", r.returncode == 0, detail))
        kubectl(settings, c, "-n", "default", "delete", "pod", "core1-smoke", "--ignore-not-found", "--wait=false", check=False)
    return results


def require_kubeconfigs(settings):
    missing = [c.name for c in settings.clusters if not c.kubeconfig(settings).exists()]
    if missing:
        raise CommandError(f"no kubeconfig for {', '.join(missing)}; run: ./core1 up")

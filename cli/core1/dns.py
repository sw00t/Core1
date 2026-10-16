"""Cluster DNS: *.<cluster>.localhost resolves to that cluster's k3d load balancer from every pod.

Browsers resolve *.localhost to 127.0.0.1, where k3d publishes the same ports. Inside the clusters the name must
reach the load balancer container on the shared docker network instead. Docker Desktop's resolver (CoreDNS's
upstream) already knows every container on that network, so a rewrite to k3d-<cluster>-serverlb is enough.
"""
import json

from .shell import log

CONFIGMAP = "coredns-custom"
KEY = "core1-localhost.override"


def override(settings):
    blocks = []
    for c in settings.clusters:
        blocks.append(
            "rewrite stop {\n"
            f"  name regex ^(.+\\.)?{c.name}\\.localhost\\.$ k3d-{c.name}-serverlb.\n"
            "  answer auto\n"
            "}\n"
        )
    return "".join(blocks)


def ensure_dns(settings, cluster):
    from .clusters import kubectl  # local import: clusters imports nothing from here

    want = override(settings)
    r = kubectl(settings, cluster, "-n", "kube-system", "get", "configmap", CONFIGMAP, "-o", "json", check=False)
    if r.returncode == 0 and json.loads(r.stdout).get("data", {}).get(KEY) == want:
        return False
    manifest = {
        "apiVersion": "v1", "kind": "ConfigMap",
        "metadata": {"name": CONFIGMAP, "namespace": "kube-system",
                     "labels": {"app.kubernetes.io/part-of": "core1"}},
        "data": {KEY: want},
    }
    kubectl(settings, cluster, "apply", "-f", "-", input=json.dumps(manifest))
    kubectl(settings, cluster, "-n", "kube-system", "rollout", "restart", "deploy/coredns")
    kubectl(settings, cluster, "-n", "kube-system", "rollout", "status", "deploy/coredns", "--timeout=120s", timeout=150)
    log(f"{cluster.name}: CoreDNS resolves *.<cluster>.localhost to the k3d load balancers")
    return True

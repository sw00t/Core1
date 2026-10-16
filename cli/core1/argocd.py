"""Argo CD in mgmt: bootstrap install, cluster and repo registration, and the status glance view.

Bootstrap is the only place Core1 applies manifests directly. After the root Application exists, Argo CD owns
everything, including itself, from core1-gitops.
"""
import base64
import json
import time
from datetime import datetime, timezone

from .clusters import kubectl
from .shell import CommandError, docker_env, log, run

NS = "argocd"
POLL_SECONDS = 30
BOOTSTRAP_PATH = "platform/argocd/base"
COMPONENT_DEPLOYMENTS = ("argocd-server", "argocd-repo-server", "argocd-applicationset-controller", "argocd-redis")


def mgmt(settings):
    return settings.cluster("mgmt")


def installed(settings):
    r = kubectl(settings, mgmt(settings), "-n", NS, "get", "deploy", "argocd-server", check=False)
    return r.returncode == 0


def apply_json(settings, cluster, obj):
    kubectl(settings, cluster, "apply", "-f", "-", input=json.dumps(obj))


def install(settings, checkout):
    """Render platform/argocd/base from the GitOps checkout and apply it server-side. The base is the chart and
    its CRDs only; the mgmt overlay adds objects whose CRDs (Gateway API, External Secrets) arrive later through
    Argo CD itself, so applying the overlay on a fresh cluster would fail."""
    log("installing Argo CD into mgmt (bootstrap)")
    rendered = run([settings.tool("kustomize"), "build", "--enable-helm", str(checkout / BOOTSTRAP_PATH)],
                   env=docker_env(settings), timeout=300).stdout
    kubectl(settings, mgmt(settings), "apply", "--server-side", "--force-conflicts", "-f", "-", input=rendered, timeout=300)
    wait_ready(settings)


def controller_running(settings):
    r = kubectl(settings, mgmt(settings), "-n", NS, "get", "pod", "argocd-application-controller-0",
                "-o", "jsonpath={.status.containerStatuses[0].ready}", check=False)
    return r.returncode == 0 and r.stdout.strip() == "true"


def repair_if_down(settings, checkout, grace=60):
    """Bootstrap repair: if the application controller is not running, Argo CD cannot apply its own fix from
    git. Re-apply Argo CD from the merged main (the same render the first install used)."""
    deadline = time.monotonic() + grace
    while time.monotonic() < deadline:
        if controller_running(settings):
            return False
        time.sleep(5)
    log("Argo CD application controller is not running; re-applying Argo CD from main (bootstrap repair)")
    # A sync of Argo CD itself that was cut short stays recorded on its Application; on restart the controller
    # would resume it and re-apply the old revision. Drop it first.
    kubectl(settings, mgmt(settings), "-n", NS, "patch", "application", "argocd-mgmt", "--type", "merge",
            "-p", json.dumps({"operation": None, "status": {"operationState": None}}), check=False)
    rendered = run([settings.tool("kustomize"), "build", "--enable-helm", str(checkout / BOOTSTRAP_PATH)],
                   env=docker_env(settings), timeout=300).stdout
    kubectl(settings, mgmt(settings), "apply", "--server-side", "--force-conflicts", "-f", "-", input=rendered, timeout=300)
    # A StatefulSet does not replace a pod that never became ready; delete it so the new spec takes effect.
    kubectl(settings, mgmt(settings), "-n", NS, "delete", "pod", "argocd-application-controller-0", "--wait=false", check=False)
    wait_ready(settings)
    return True


def wait_ready(settings, timeout=300):
    m = mgmt(settings)
    for d in COMPONENT_DEPLOYMENTS:
        kubectl(settings, m, "-n", NS, "rollout", "status", f"deploy/{d}", f"--timeout={timeout}s", timeout=timeout + 15)
    kubectl(settings, m, "-n", NS, "rollout", "status", "statefulset/argocd-application-controller",
            f"--timeout={timeout}s", timeout=timeout + 15)


def _secret(name, labels, string_data):
    return {"apiVersion": "v1", "kind": "Secret", "type": "Opaque",
            "metadata": {"name": name, "namespace": NS, "labels": {"app.kubernetes.io/part-of": "core1", **labels}},
            "stringData": string_data}


def register_clusters(settings):
    """Cluster secrets in mgmt for mgmt (in-cluster) and for stage and prod (ServiceAccount token over core1 net)."""
    m = mgmt(settings)
    apply_json(settings, m, _secret("cluster-mgmt", {"argocd.argoproj.io/secret-type": "cluster", "core1.io/cluster": "mgmt"},
                                    {"name": "mgmt", "server": "https://kubernetes.default.svc",
                                     "config": json.dumps({"tlsClientConfig": {"insecure": False}})}))
    for c in settings.clusters:
        if c.name == "mgmt":
            continue
        manager = [
            {"apiVersion": "v1", "kind": "ServiceAccount",
             "metadata": {"name": "argocd-manager", "namespace": "kube-system", "labels": {"app.kubernetes.io/part-of": "core1"}}},
            {"apiVersion": "rbac.authorization.k8s.io/v1", "kind": "ClusterRoleBinding",
             "metadata": {"name": "argocd-manager", "labels": {"app.kubernetes.io/part-of": "core1"}},
             "roleRef": {"apiGroup": "rbac.authorization.k8s.io", "kind": "ClusterRole", "name": "cluster-admin"},
             "subjects": [{"kind": "ServiceAccount", "name": "argocd-manager", "namespace": "kube-system"}]},
            {"apiVersion": "v1", "kind": "Secret", "type": "kubernetes.io/service-account-token",
             "metadata": {"name": "argocd-manager-token", "namespace": "kube-system",
                          "annotations": {"kubernetes.io/service-account.name": "argocd-manager"},
                          "labels": {"app.kubernetes.io/part-of": "core1"}}},
        ]
        apply_json(settings, c, {"apiVersion": "v1", "kind": "List", "items": manager})
        token = ca = ""
        for _ in range(30):
            r = kubectl(settings, c, "-n", "kube-system", "get", "secret", "argocd-manager-token", "-o", "json")
            data = json.loads(r.stdout).get("data", {})
            token, ca = data.get("token", ""), data.get("ca.crt", "")
            if token and ca:
                break
            time.sleep(1)
        if not token:
            raise CommandError(f"{c.name}: argocd-manager token was not issued")
        config = {"bearerToken": base64.b64decode(token).decode(), "tlsClientConfig": {"caData": ca}}
        apply_json(settings, m, _secret(f"cluster-{c.name}",
                                        {"argocd.argoproj.io/secret-type": "cluster", "core1.io/cluster": c.name},
                                        {"name": c.name, "server": f"https://k3d-{c.name}-serverlb:6443",
                                         "config": json.dumps(config)}))
    log("clusters registered with Argo CD: mgmt, stage, prod")


def ensure_repo_secret(settings):
    """Repo credentials from .env. Created only if missing: once External Secrets owns it (phase 2c), it stays."""
    m = mgmt(settings)
    if kubectl(settings, m, "-n", NS, "get", "secret", "repo-core1-gitops", check=False).returncode == 0:
        return
    if kubectl(settings, m, "-n", NS, "get", "externalsecret", "repo-core1-gitops", check=False).returncode == 0:
        return  # External Secrets will (re)create it
    token = settings.token("argocd")
    if not token:
        raise CommandError("CORE1_GITHUB_TOKEN_ARGOCD missing in .env")
    apply_json(settings, m, _secret("repo-core1-gitops", {"argocd.argoproj.io/secret-type": "repository"},
                                    {"type": "git", "url": settings.gitops_url, "username": "core1-argocd",
                                     "password": token}))
    log("Argo CD repo credentials created (bootstrap)")


def handover_repo_secret(settings, timeout=180):
    """Once the ExternalSecret exists, replace the bootstrap copy with the one External Secrets owns."""
    m = mgmt(settings)
    deadline = time.monotonic() + timeout
    while kubectl(settings, m, "-n", NS, "get", "externalsecret", "repo-core1-gitops", check=False).returncode != 0:
        if time.monotonic() > deadline:
            raise CommandError("ExternalSecret repo-core1-gitops not created by Argo CD; check the argocd-mgmt app")
        time.sleep(5)
    r = kubectl(settings, m, "-n", NS, "get", "secret", "repo-core1-gitops", "-o", "json", check=False)
    if r.returncode == 0 and json.loads(r.stdout)["metadata"].get("ownerReferences"):
        return False  # already owned
    if r.returncode == 0:
        kubectl(settings, m, "-n", NS, "delete", "secret", "repo-core1-gitops")
    kubectl(settings, m, "-n", NS, "annotate", "externalsecret", "repo-core1-gitops",
            f"force-sync={int(time.time())}", "--overwrite")
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        r = kubectl(settings, m, "-n", NS, "get", "secret", "repo-core1-gitops", "-o", "json", check=False)
        if r.returncode == 0 and json.loads(r.stdout)["metadata"].get("ownerReferences"):
            log("Argo CD repo credentials now come from OpenBao through External Secrets")
            return True
        time.sleep(5)
    raise CommandError("External Secrets did not create repo-core1-gitops; check the openbao ClusterSecretStore in mgmt")


def apply_root(settings, checkout):
    kubectl(settings, mgmt(settings), "apply", "-f", str(checkout / "bootstrap/root.yaml"))


def refresh_all(settings):
    """Ask Argo CD to look at git now instead of waiting for the next poll."""
    kubectl(settings, mgmt(settings), "-n", NS, "annotate", "applications", "--all",
            "argocd.argoproj.io/refresh=normal", "--overwrite", check=False)


# ---- status ----

def applications(settings):
    r = kubectl(settings, mgmt(settings), "-n", NS, "get", "applications.argoproj.io", "-o", "json", check=False)
    if r.returncode != 0:
        return []
    apps = []
    for a in json.loads(r.stdout).get("items", []):
        st = a.get("status", {})
        apps.append({
            "name": a["metadata"]["name"],
            "cluster": a["metadata"].get("labels", {}).get("core1.io/cluster", "?"),
            "sync": st.get("sync", {}).get("status", "Unknown"),
            "health": st.get("health", {}).get("status", "Unknown"),
            "revision": st.get("sync", {}).get("revision", ""),
            "reconciled_at": st.get("reconciledAt"),
        })
    return apps


def _age(ts, now=None):
    if not ts:
        return None
    t = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    return ((now or datetime.now(timezone.utc)) - t).total_seconds()


def summarize(apps, expected, head, behind_fn=None, now=None):
    """Per-cluster rows for the glance view. behind_fn(revision) -> commits behind main (optional)."""
    rows = []
    for cluster, want in expected.items():
        mine = [a for a in apps if a["cluster"] == cluster]
        synced = sum(a["sync"] == "Synced" for a in mine)
        healthy = sum(a["health"] == "Healthy" for a in mine)
        revs = {a["revision"] for a in mine if a["revision"]}
        if not mine:
            position = "nothing to deploy" if want == 0 else "no apps yet"
        elif head and revs == {head}:
            position = "at HEAD"
        elif head and behind_fn:
            behind = max((behind_fn(r) for r in revs), default=0)
            position = f"{behind} commit{'s' if behind != 1 else ''} behind" if behind else "at HEAD"
        else:
            position = "revision unknown"
        ages = [x for x in (_age(a["reconciled_at"], now) for a in mine) if x is not None]
        last = min(ages) if ages else None
        ok = len(mine) == want and synced == want and healthy == want and (
            position == "at HEAD" or (want == 0 and not mine))
        rows.append({"cluster": cluster, "apps": len(mine), "expected": want, "synced": synced, "healthy": healthy,
                     "position": position, "last_reconcile_s": last,
                     "next_poll_s": max(0, POLL_SECONDS - last) if last is not None else None, "ok": ok})
    return rows


def format_rows(rows, head):
    out = [f"Argo CD  main {head[:7] if head else '?'}, polls every {POLL_SECONDS}s"]
    for r in rows:
        timing = ""
        if r["last_reconcile_s"] is not None:
            timing = f"  checked {int(r['last_reconcile_s'])}s ago, next ~{int(r['next_poll_s'])}s"
        out.append(f"  {'ok  ' if r['ok'] else 'WAIT'}  {r['cluster']:6} apps {r['apps']}/{r['expected']}  "
                   f"synced {r['synced']}  healthy {r['healthy']}  {r['position']}{timing}")
    return "\n".join(out)

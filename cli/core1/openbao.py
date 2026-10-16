"""OpenBao in mgmt: initialise once, unseal after every start, configure auth and policies, seed secrets.

Everything runs through `kubectl exec` into openbao-0 with the root token passed on stdin, never as an argument.
The unseal key and root token live in .work/openbao/init.json (chmod 600, git-ignored, removed by nuke).
Lab trade-off: a real estate would auto-unseal from a KMS and never keep the root token.
"""
import base64
import json
import time

from .clusters import kubectl
from .shell import CommandError, log

NS = "openbao"
POD = "openbao-0"
MOUNT = "core1"


def init_file(settings):
    return settings.work_dir / "openbao" / "init.json"


def present(checkout):
    """Does main deploy OpenBao?"""
    return (checkout / "platform" / "openbao" / "overlays" / "mgmt").is_dir()


def _exec(settings, script, stdin="", check=True, timeout=60):
    return kubectl(settings, settings.cluster("mgmt"), "-n", NS, "exec", "-i", POD, "-c", "openbao", "--",
                   "sh", "-c", script, input=stdin, check=check, timeout=timeout)


def _with_token(settings, script, stdin_rest="", check=True):
    """Run SCRIPT with BAO_TOKEN set from the first stdin line; the rest of stdin follows."""
    token = json.loads(init_file(settings).read_text())["root_token"]
    full = "read -r BAO_TOKEN; export BAO_TOKEN; export BAO_ADDR=http://127.0.0.1:8200; " + script
    return _exec(settings, full, stdin=token + "\n" + stdin_rest, check=check)


def wait_running(settings, timeout=600):
    """openbao-0 stays unready while sealed, so wait for the container to run, not for Ready."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        r = kubectl(settings, settings.cluster("mgmt"), "-n", NS, "get", "pod", POD, "-o",
                    "jsonpath={.status.containerStatuses[0].state.running.startedAt}", check=False)
        if r.returncode == 0 and r.stdout.strip():
            return
        time.sleep(5)
    raise CommandError(f"{POD} not running after {timeout}s (is the openbao-mgmt app synced?)")


def status(settings):
    r = _exec(settings, "BAO_ADDR=http://127.0.0.1:8200 bao status -format=json", check=False)
    try:
        return json.loads(r.stdout)
    except json.JSONDecodeError as e:
        raise CommandError(f"bao status: {(r.stderr or r.stdout).strip()[:300]}") from e


def ensure_unsealed(settings):
    st = status(settings)
    path = init_file(settings)
    if not st.get("initialized"):
        log("initialising OpenBao (one key share; kept in .work/openbao/init.json)")
        out = _exec(settings, "BAO_ADDR=http://127.0.0.1:8200 bao operator init -key-shares=1 -key-threshold=1 -format=json").stdout
        data = json.loads(out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch(mode=0o600)
        path.write_text(json.dumps({"unseal_key": data["unseal_keys_b64"][0], "root_token": data["root_token"]}))
        path.chmod(0o600)
        st = status(settings)
    if not path.exists():
        raise CommandError("OpenBao is initialised but .work/openbao/init.json is missing; `./core1 nuke` and `up` again")
    if st.get("sealed"):
        key = json.loads(path.read_text())["unseal_key"]
        _exec(settings, "read -r K; BAO_ADDR=http://127.0.0.1:8200 bao operator unseal \"$K\" >/dev/null", stdin=key + "\n")
        log("OpenBao unsealed")
    for _ in range(30):
        if not status(settings).get("sealed"):
            return
        time.sleep(2)
    raise CommandError("OpenBao still sealed")


def _cluster_ca_pem(settings, cluster):
    r = kubectl(settings, cluster, "config", "view", "--raw", "--minify", "-o",
                "jsonpath={.clusters[0].cluster.certificate-authority-data}")
    return base64.b64decode(r.stdout.strip()).decode()


def policy(cluster_name):
    return (f'path "{MOUNT}/data/{cluster_name}/*" {{ capabilities = ["read"] }}\n'
            f'path "{MOUNT}/data/shared/*" {{ capabilities = ["read"] }}\n')


def configure(settings):
    """Idempotent: KV mount, one Kubernetes auth mount per cluster, read policy and role per cluster."""
    lines = [
        f"bao secrets list -format=json | grep -q '\"{MOUNT}/\"' || bao secrets enable -path={MOUNT} -version=2 kv >/dev/null",
    ]
    for c in settings.clusters:
        mount = f"kubernetes-{c.name}"
        lines.append(f"bao auth list -format=json | grep -q '\"{mount}/\"' || bao auth enable -path={mount} kubernetes >/dev/null")
        if c.name == "mgmt":
            # in-cluster: OpenBao's own ServiceAccount reviews tokens
            lines.append(f"bao write auth/{mount}/config kubernetes_host=https://kubernetes.default.svc >/dev/null")
        else:
            # remote: the client's own token reviews itself (ESO has auth-delegator), over the core1 network
            ca = _cluster_ca_pem(settings, c).replace("'", "")
            lines.append(f"bao write auth/{mount}/config kubernetes_host=https://k3d-{c.name}-serverlb:6443 "
                         f"kubernetes_ca_cert='{ca}' disable_local_ca_jwt=true >/dev/null")
        lines.append(f"printf '%s' '{policy(c.name)}' | bao policy write core1-{c.name}-read - >/dev/null")
        lines.append(f"bao write auth/{mount}/role/external-secrets bound_service_account_names=external-secrets "
                     f"bound_service_account_namespaces=external-secrets token_policies=core1-{c.name}-read "
                     f"token_ttl=15m token_max_ttl=1h >/dev/null")
    _with_token(settings, " && ".join(lines))
    log("OpenBao configured: KV core1/, Kubernetes auth for mgmt, stage, prod, read-only policies")


def put(settings, path, data):
    _with_token(settings, f"bao kv put -mount={MOUNT} {path} - >/dev/null", stdin_rest=json.dumps(data))


def get(settings, path):
    r = _with_token(settings, f"bao kv get -mount={MOUNT} -format=json {path}", check=False)
    if r.returncode != 0:
        return None
    return json.loads(r.stdout)["data"]["data"]


def seed_secrets(settings):
    """GitHub tokens from .env (written every run, so a rotated token in .env reaches the cluster)."""
    tokens = {"argocd_token": settings.token("argocd"), "automation_token": settings.token("automation")}
    if not all(tokens.values()):
        raise CommandError("GitHub tokens missing in .env")
    if get(settings, "mgmt/github") != tokens:
        put(settings, "mgmt/github", tokens)
        log("OpenBao: core1/mgmt/github updated from .env")
    ensure_generated(settings, "mgmt/keycloak", KEYCLOAK_KEYS)
    for env in ("stage", "prod"):
        ensure_generated(settings, f"{env}/valkey", ("password",))


KEYCLOAK_KEYS = ("admin_password", "argocd_client_secret", "platform_admin_password", "platform_viewer_password")


def ensure_generated(settings, path, keys):
    """Random values for KEYS at PATH, generated once and kept; missing keys are added, existing ones untouched."""
    import secrets as pysecrets

    current = get(settings, path) or {}
    missing = [k for k in keys if not current.get(k)]
    if missing:
        current.update({k: pysecrets.token_urlsafe(24) for k in missing})
        put(settings, path, current)
        log(f"OpenBao: generated {', '.join(missing)} at core1/{path}")
    return current

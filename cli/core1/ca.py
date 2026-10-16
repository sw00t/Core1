"""The lab's root CA. Created once with openssl and kept in .ca/ (git-ignored) so a trusted CA survives `nuke`;
`nuke --all` removes it. cert-manager in every cluster issues gateway certificates from it."""
import json

from .shell import log, run

SECRET = "core1-ca"
NAMESPACE = "cert-manager"


def ca_dir(settings):
    return settings.root / ".ca"


def ensure_ca(settings):
    d = ca_dir(settings)
    crt, key = d / "ca.crt", d / "ca.key"
    if crt.exists() and key.exists():
        return crt, key
    d.mkdir(mode=0o700, exist_ok=True)
    run(["openssl", "req", "-x509", "-new", "-nodes", "-sha256", "-days", "3650",
         "-newkey", "ec", "-pkeyopt", "ec_paramgen_curve:prime256v1",
         "-keyout", key, "-out", crt, "-subj", "/O=Core1 Lab/CN=Core1 Lab Root CA",
         "-addext", "basicConstraints=critical,CA:TRUE,pathlen:0",
         "-addext", "keyUsage=critical,keyCertSign,cRLSign"])
    key.chmod(0o600)
    log(f"created the lab root CA in {d.relative_to(settings.root)}/ (trust it in macOS to avoid browser warnings: docs/host.md)")
    return crt, key


def apply_ca_secret(settings, cluster):
    """Bootstrap copy of the CA into cert-manager's namespace (External Secrets takes over in phase 2c)."""
    from .clusters import kubectl

    crt, key = ensure_ca(settings)
    ns = {"apiVersion": "v1", "kind": "Namespace", "metadata": {"name": NAMESPACE}}
    kubectl(settings, cluster, "apply", "-f", "-", input=json.dumps(ns))
    secret = kubectl(settings, cluster, "-n", NAMESPACE, "create", "secret", "tls", SECRET,
                     f"--cert={crt}", f"--key={key}", "--dry-run=client", "-o", "json").stdout
    kubectl(settings, cluster, "apply", "-f", "-", input=secret)

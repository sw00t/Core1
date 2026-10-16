"""Pinned k3d, kubectl and helm in .bin, downloaded with checksum verification.

Nothing is installed system-wide. Re-running is a no-op when versions match. K3D_BIN, KUBECTL_BIN or
HELM_BIN (environment or .env) copy an existing binary into .bin instead, for networks that block a
download host.
"""
import hashlib
import platform
import shutil
import tarfile
import tempfile
from pathlib import Path

from .shell import CommandError, log, run, warn

TOOLS = ("k3d", "kubectl", "helm")
VERSION_KEYS = {"k3d": "K3D_VERSION", "kubectl": "KUBECTL_VERSION", "helm": "HELM_VERSION"}


def host_os_arch():
    os_name = platform.system().lower()
    arch = {"x86_64": "amd64", "amd64": "amd64", "arm64": "arm64", "aarch64": "arm64"}.get(platform.machine().lower())
    if not arch:
        raise SystemExit(f"unsupported CPU architecture: {platform.machine()}")
    return os_name, arch


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def checksum_from_list(text, filename):
    """Find FILENAME in a sha256sum-style list ('<hash>  <name>' per line)."""
    for line in text.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[-1].lstrip("*") == filename:
            return parts[0]
    raise SystemExit(f"checksum for {filename} not found")


def fetch(dest, *urls):
    """Download the first URL that works. curl handles retries; IPv4 first, as some networks break IPv6."""
    for url in urls:
        for extra in (["-4"], []):
            r = run(["curl", *extra, "-fsSL", "--retry", "2", "--retry-delay", "3", "--retry-all-errors",
                     "-o", dest, url], check=False)
            if r.returncode == 0:
                return
        warn(f"download failed from {url}")
    raise SystemExit(f"download failed: {urls[0]}")


def installed_version(settings, name):
    marker = settings.bin_dir / f".{name}.version"
    if (settings.bin_dir / name).exists() and marker.exists():
        return marker.read_text().strip()
    return None


def _install(settings, name, src, version):
    settings.bin_dir.mkdir(parents=True, exist_ok=True)
    dest = settings.bin_dir / name
    shutil.copyfile(src, dest)
    dest.chmod(0o755)
    (settings.bin_dir / f".{name}.version").write_text(version)


def _download(name, version, os_name, arch, tmp):
    tmp = Path(tmp)
    if name == "k3d":
        base = f"https://github.com/k3d-io/k3d/releases/download/{version}"
        fname = f"k3d-{os_name}-{arch}"
        fetch(tmp / fname, f"{base}/{fname}")
        fetch(tmp / "checksums.txt", f"{base}/checksums.txt")
        want = checksum_from_list((tmp / "checksums.txt").read_text(), fname)
        binary = tmp / fname
    elif name == "kubectl":
        path = f"release/{version}/bin/{os_name}/{arch}/kubectl"
        hosts = ["https://dl.k8s.io", "https://cdn.dl.k8s.io"]
        fetch(tmp / "kubectl", *[f"{h}/{path}" for h in hosts])
        fetch(tmp / "kubectl.sha256", *[f"{h}/{path}.sha256" for h in hosts])
        want = (tmp / "kubectl.sha256").read_text().split()[0]
        binary = tmp / "kubectl"
    elif name == "helm":
        tgz = f"helm-{version}-{os_name}-{arch}.tar.gz"
        fetch(tmp / tgz, f"https://get.helm.sh/{tgz}")
        fetch(tmp / f"{tgz}.sha256sum", f"https://get.helm.sh/{tgz}.sha256sum")
        want = (tmp / f"{tgz}.sha256sum").read_text().split()[0]
        got = sha256_of(tmp / tgz)
        if got != want:
            raise SystemExit(f"checksum mismatch for {tgz}: got {got} want {want}")
        with tarfile.open(tmp / tgz) as tf:
            member = tf.getmember(f"{os_name}-{arch}/helm")
            tf.extract(member, tmp, filter="data")
        return tmp / f"{os_name}-{arch}" / "helm"
    else:
        raise ValueError(name)
    got = sha256_of(binary)
    if got != want:
        raise SystemExit(f"checksum mismatch for {name}: got {got} want {want}")
    return binary


def ensure_tools(settings):
    os_name, arch = host_os_arch()
    for name in TOOLS:
        version = settings.version(VERSION_KEYS[name])
        override = settings.get(f"{name.upper()}_BIN")
        if override:
            if not Path(override).is_file():
                raise SystemExit(f"{name.upper()}_BIN={override} is not a file")
            if installed_version(settings, name) != version:
                _install(settings, name, override, version)
                log(f"{name}: using {override} (declared {version})")
            continue
        if installed_version(settings, name) == version:
            continue
        log(f"downloading {name} {version} ({os_name}/{arch})")
        with tempfile.TemporaryDirectory() as tmp:
            _install(settings, name, _download(name, version, os_name, arch, tmp), version)
    log(f"tools ready in {settings.bin_dir.relative_to(settings.root)}")


def tool_version_report(settings):
    """[(name, wanted, installed or None)]"""
    return [(n, settings.version(VERSION_KEYS[n]), installed_version(settings, n)) for n in TOOLS]


def require_tools(settings):
    missing = [n for n, want, have in tool_version_report(settings) if have != want]
    if missing:
        raise CommandError(f"tools missing or wrong version: {', '.join(missing)}; run: ./core1 up")

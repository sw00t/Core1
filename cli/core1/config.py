"""Settings: pinned versions, optional .env overrides, cluster table, ports, paths."""
import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

CLUSTER_NAMES = ("mgmt", "stage", "prod")
NETWORK = "core1"
REGISTRY_NAME = "registry"  # k3d prefixes it: container k3d-registry
REGISTRY_CONTAINER = "k3d-registry"
REGISTRY_INTERNAL_PORT = 5000
DEFAULT_PORT_BASE = 17000


def parse_env_file(path):
    """KEY=VALUE lines; blank lines and # comments ignored; surrounding quotes stripped."""
    values = {}
    if not path.exists():
        return values
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


@dataclass(frozen=True)
class Cluster:
    name: str
    index: int  # 1-based position in CLUSTER_NAMES; selects the port block
    port_base: int

    @property
    def block(self):
        return self.port_base + 100 * self.index

    @property
    def api_port(self):
        return self.block + 43

    @property
    def http_port(self):
        return self.block + 80

    @property
    def https_port(self):
        return self.block + 81

    @property
    def server_container(self):
        return f"k3d-{self.name}-server-0"

    def kubeconfig(self, settings):
        return settings.kube_dir / f"{self.name}.yaml"


class Settings:
    def __init__(self, root=ROOT, environ=None):
        environ = os.environ if environ is None else environ
        self.root = Path(root)
        self.versions = parse_env_file(self.root / "versions.env")
        # precedence: process environment, then .env, then versions.env
        self.overrides = parse_env_file(self.root / ".env")
        self.environ = environ
        self.port_base = int(self.get("CORE1_PORT_BASE", DEFAULT_PORT_BASE))
        self.clusters = [Cluster(n, i + 1, self.port_base) for i, n in enumerate(CLUSTER_NAMES)]
        self.bin_dir = self.root / ".bin"
        self.kube_dir = self.root / ".kube"
        self.work_dir = self.root / ".work"
        self.venv_dir = self.root / ".venv"

    def get(self, key, default=None):
        for source in (self.environ, self.overrides, self.versions):
            if source.get(key):
                return source[key]
        return default

    def version(self, key):
        value = self.get(key)
        if not value:
            raise SystemExit(f"versions.env is missing {key}")
        return value

    @property
    def registry_port(self):
        return self.port_base

    @property
    def registry_host_url(self):
        return f"http://127.0.0.1:{self.registry_port}"

    @property
    def registry_use(self):
        """Address clusters are told to use (k3d writes the containerd mirror for it)."""
        return f"{REGISTRY_CONTAINER}:{self.registry_port}"

    def all_ports(self):
        ports = [self.registry_port]
        for c in self.clusters:
            ports += [c.api_port, c.http_port, c.https_port]
        return ports

    def cluster(self, name):
        for c in self.clusters:
            if c.name == name:
                return c
        raise KeyError(name)

    def tool(self, name):
        return self.bin_dir / name

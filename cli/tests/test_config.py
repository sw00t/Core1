from core1.config import ROOT, Settings, parse_env_file


def write(path, text):
    path.write_text(text)
    return path


def test_parse_env_file(tmp_path):
    p = write(tmp_path / "x.env", '# comment\n\nA=1\nB="two"\nC=\'three\'\nnot a line\nD=x=y\n')
    assert parse_env_file(p) == {"A": "1", "B": "two", "C": "three", "D": "x=y"}


def test_parse_missing_file(tmp_path):
    assert parse_env_file(tmp_path / "nope.env") == {}


def test_port_blocks_default():
    s = Settings(root=ROOT, environ={})
    assert s.registry_port == 17000
    assert [(c.name, c.api_port, c.http_port, c.https_port) for c in s.clusters] == [
        ("mgmt", 17143, 17180, 17181),
        ("stage", 17243, 17280, 17281),
        ("prod", 17343, 17380, 17381),
    ]
    assert len(set(s.all_ports())) == 10


def test_port_base_override_precedence(tmp_path):
    write(tmp_path / "versions.env", "K3D_VERSION=v1\n")
    write(tmp_path / ".env", "CORE1_PORT_BASE=20000\nK3D_VERSION=v2\n")
    s = Settings(root=tmp_path, environ={})
    assert s.registry_port == 20000
    assert s.cluster("prod").api_port == 20343
    assert s.version("K3D_VERSION") == "v2"  # .env beats versions.env
    s = Settings(root=tmp_path, environ={"K3D_VERSION": "v3"})
    assert s.version("K3D_VERSION") == "v3"  # environment beats .env


def test_versions_env_has_every_pin():
    s = Settings(root=ROOT, environ={})
    for key in ("K3D_VERSION", "KUBECTL_VERSION", "HELM_VERSION", "K3S_IMAGE", "K3D_PROXY_IMAGE",
                "K3D_TOOLS_IMAGE", "REGISTRY_IMAGE", "PYTHON_VERSION"):
        assert s.version(key)


def test_registry_use_and_kubeconfig_paths():
    s = Settings(root=ROOT, environ={})
    assert s.registry_use == "k3d-registry:17000"
    assert s.cluster("stage").kubeconfig(s) == ROOT / ".kube" / "stage.yaml"
    assert s.cluster("mgmt").server_container == "k3d-mgmt-server-0"

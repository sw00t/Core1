import pytest
from typer.testing import CliRunner

from core1 import clusters
from core1.app import app
from core1.config import Settings

runner = CliRunner()


def test_help_lists_design_commands():
    r = runner.invoke(app, ["--help"])
    assert r.exit_code == 0
    for cmd in ("doctor", "up", "status", "endpoints", "nuke", "pack", "scenario", "reset", "test"):
        assert cmd in r.output


@pytest.mark.parametrize("args,phase", [
    (["pack", "list"], "6"),
    (["pack", "install", "telco"], "6"),
    (["scenario", "run", "1"], "7"),
    (["reset", "platform"], "2"),
    (["test", "pack-seam"], "6"),
    (["test", "all"], "8"),
    (["up", "--profile", "lite"], "8"),
])
def test_later_phase_commands_exit_2(args, phase):
    r = runner.invoke(app, args)
    assert r.exit_code == 2
    assert f"phase {phase}" in r.output


def test_nuke_asks_first():
    r = runner.invoke(app, ["nuke"], input="n\n")
    assert r.exit_code == 1
    assert "Delete clusters mgmt, stage, prod" in r.output


def test_create_args_shape():
    s = Settings(environ={})
    args = clusters.create_args(s, s.cluster("stage"))
    joined = " ".join(args)
    assert args[:3] == ["cluster", "create", "stage"]
    assert "--servers 1 --agents 1" in joined
    assert "--network core1" in joined
    assert "--registry-use k3d-registry:17000" in joined
    assert "--api-port 127.0.0.1:17243" in joined
    assert "127.0.0.1:17280:80@loadbalancer" in joined
    assert "127.0.0.1:17281:443@loadbalancer" in joined
    assert "--disable=traefik@server:*" in joined
    assert "servicelb" not in joined
    assert "--kubeconfig-update-default=false" in joined


def test_is_running():
    assert clusters.is_running({"servers": (1, 1), "agents": (1, 1)})
    assert not clusters.is_running({"servers": (1, 1), "agents": (0, 1)})
    assert not clusters.is_running({"servers": (0, 0), "agents": (0, 0)})

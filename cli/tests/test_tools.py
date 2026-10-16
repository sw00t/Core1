import hashlib

import pytest

from core1 import tools
from core1.config import Settings


def test_checksum_from_list():
    text = "aaa  k3d-linux-amd64\nbbb  k3d-darwin-arm64\nccc *k3d-windows-amd64.exe\n"
    assert tools.checksum_from_list(text, "k3d-darwin-arm64") == "bbb"
    assert tools.checksum_from_list(text, "k3d-windows-amd64.exe") == "ccc"
    with pytest.raises(SystemExit):
        tools.checksum_from_list(text, "k3d-plan9-mips")


def test_sha256_of(tmp_path):
    p = tmp_path / "f"
    p.write_bytes(b"core1")
    assert tools.sha256_of(p) == hashlib.sha256(b"core1").hexdigest()


def test_installed_version_and_override(tmp_path):
    (tmp_path / "versions.env").write_text("K3D_VERSION=v9\nKUBECTL_VERSION=v8\nHELM_VERSION=v7\n")
    s = Settings(root=tmp_path, environ={})
    assert tools.installed_version(s, "k3d") is None
    fake = tmp_path / "fake-k3d"
    fake.write_text("#!/bin/sh\n")
    tools._install(s, "k3d", fake, "v9")
    assert tools.installed_version(s, "k3d") == "v9"
    assert (tmp_path / ".bin" / "k3d").stat().st_mode & 0o111
    report = {n: (want, have) for n, want, have in tools.tool_version_report(s)}
    assert report["k3d"] == ("v9", "v9")
    assert report["kubectl"] == ("v8", None)

import json
from datetime import datetime, timezone

from core1 import argocd, gitops
from core1.config import ROOT, Settings, parse_env_file
from core1.doctor import Report, check_tokens


def settings(**env):
    return Settings(root=ROOT, environ=env)


def test_ci_tool_pins_match_host_pins():
    host = parse_env_file(ROOT / "versions.env")
    ci = parse_env_file(ROOT / "gitops" / "ci" / "versions.env")
    for key in ("KUSTOMIZE_VERSION", "KUBECONFORM_VERSION", "HELM_VERSION", "KYVERNO_VERSION"):
        assert ci[key] == host[key], key
    assert ci["KUBERNETES_VERSION"] in host["K3S_IMAGE"].replace("-k3s1", "")


def test_template_hash_is_stable_and_url_sensitive():
    a = gitops.template_hash(settings())
    assert a == gitops.template_hash(settings())
    assert a != gitops.template_hash(settings(CORE1_GITOPS_REPO="someone/else"))


def test_render_fills_repo_url():
    s = settings()
    text = gitops.render(s, gitops.template_files(s)[0].__class__("bootstrap/root.yaml")).decode()
    assert gitops.PLACEHOLDER not in text
    assert "https://github.com/sw00t/core1-gitops.git" in text


def test_template_stays_inside_owned_paths():
    for rel in gitops.template_files(settings()):
        assert rel.parts[0] in gitops.OWNED, rel


def test_write_tree_replaces_owned_paths_only(tmp_path):
    (tmp_path / "platform" / "old").mkdir(parents=True)
    (tmp_path / "platform" / "old" / "x.yaml").write_text("stale")
    (tmp_path / "apps").mkdir()
    (tmp_path / "apps" / "keep.yaml").write_text("mine")
    seed = gitops.write_tree(settings(), tmp_path)
    assert not (tmp_path / "platform" / "old").exists()
    assert (tmp_path / "apps" / "keep.yaml").read_text() == "mine"
    assert (tmp_path / "bootstrap" / "root.yaml").exists()
    assert json.loads((tmp_path / ".core1" / "seed.json").read_text())["template_sha256"] == seed["template_sha256"]
    assert (tmp_path / "ci" / "validate.sh").stat().st_mode & 0o111


def test_expected_apps_counts_overlays_and_root():
    counts = gitops.expected_apps(settings())
    assert counts["mgmt"] >= 2  # root + argocd
    assert set(counts) == {"mgmt", "stage", "prod"}


def _app(cluster, sync="Synced", health="Healthy", rev="abc", at="2026-10-16T10:00:00Z"):
    return {"name": f"x-{cluster}", "cluster": cluster, "sync": sync, "health": health, "revision": rev, "reconciled_at": at}


def test_summarize_at_head_and_behind():
    now = datetime(2026, 10, 16, 10, 0, 12, tzinfo=timezone.utc)
    rows = argocd.summarize([_app("mgmt"), _app("mgmt"), _app("stage", rev="old")],
                            {"mgmt": 2, "stage": 1, "prod": 0}, "abc", behind_fn=lambda r: 3, now=now)
    by = {r["cluster"]: r for r in rows}
    assert by["mgmt"]["ok"] and by["mgmt"]["position"] == "at HEAD"
    assert by["mgmt"]["last_reconcile_s"] == 12 and by["mgmt"]["next_poll_s"] == 18
    assert not by["stage"]["ok"] and by["stage"]["position"] == "3 commits behind"
    assert by["prod"]["position"] == "nothing to deploy" and by["prod"]["ok"]
    text = argocd.format_rows(rows, "abc1234def")
    assert "main abc1234" in text and "3 commits behind" in text


def test_summarize_out_of_sync_is_not_ok():
    rows = argocd.summarize([_app("mgmt", sync="OutOfSync")], {"mgmt": 1, "stage": 0, "prod": 0}, "abc")
    assert not rows[0]["ok"]


class FakeGH:
    def __init__(self, token, repo, status=200, expiry="2026-11-15 14:28:13 UTC", core1=False):
        self.status, self.expiry, self.core1 = status, expiry, core1

    def token_expiry(self):
        return self.status, self.expiry

    def can_read_repo(self, repo):
        return self.core1


def test_check_tokens(monkeypatch, capsys):
    import core1.github
    now = datetime(2026, 10, 16, tzinfo=timezone.utc)
    s = settings(CORE1_GITHUB_TOKEN_ARGOCD="a", CORE1_GITHUB_TOKEN_AUTOMATION="b")
    monkeypatch.setattr(core1.github, "GitHub", lambda t, r: FakeGH(t, r))
    r = Report()
    check_tokens(s, r, now=now)
    out = capsys.readouterr().out
    assert not r.failed and "expires in 31 days" in out

    monkeypatch.setattr(core1.github, "GitHub", lambda t, r: FakeGH(t, r, expiry="2026-10-20 00:00:00 UTC", core1=True))
    r = Report()
    check_tokens(s, r, now=now)
    out = capsys.readouterr().out
    assert not r.failed and "warn" in out and "can also read" in out

    monkeypatch.setattr(core1.github, "GitHub", lambda t, r: FakeGH(t, r, status=404))
    r = Report()
    check_tokens(s, r, now=now)
    assert r.failed


def test_missing_token_fails(monkeypatch):
    s = Settings(root=ROOT, environ={"CORE1_GITHUB_TOKEN_ARGOCD": "", "CORE1_GITHUB_TOKEN_AUTOMATION": ""})
    s.overrides = {}
    r = Report()
    check_tokens(s, r)
    assert r.failed


def test_dns_override_covers_every_cluster():
    from core1.dns import override
    text = override(settings())
    for c in ("mgmt", "stage", "prod"):
        assert f"{c}\\.localhost\\.$ k3d-{c}-serverlb." in text


def test_openbao_policy_is_read_only_and_scoped():
    from core1.openbao import policy
    p = policy("stage")
    assert 'path "core1/data/stage/*"' in p and 'path "core1/data/shared/*"' in p
    assert '"read"' in p and "create" not in p and "update" not in p and "mgmt" not in p


def test_multiline_placeholder_keeps_yaml_indentation():
    text = "a:\n  rootCA: |\n    __X__\n  b: 1"
    out = gitops._replace_indented(text, "__X__", "line1\nline2\nline3")
    assert out == "a:\n  rootCA: |\n    line1\n    line2\n    line3\n  b: 1"

"""Keep core1-gitops in step with Core1's gitops/ template, through pull requests.

Core1 owns a fixed set of paths in the GitOps repo. When the template changes, `up` opens a PR that replaces those
paths, waits for CI, and merges. Other paths (apps, packs) are never touched.
"""
import base64
import hashlib
import json
import shutil
import subprocess

from .github import GitHub, GitHubError
from .shell import CommandError, docker_env, log, run

OWNED = ("bootstrap", "platform", "ci", ".github", ".core1", ".gitignore", "README.md")
PLACEHOLDER = "__CORE1_GITOPS_URL__"
SEED_FILE = ".core1/seed.json"
SKIP_DIRS = {"charts", ".ci-bin", "__pycache__"}
AUTHOR = {"GIT_AUTHOR_NAME": "Core1 build", "GIT_AUTHOR_EMAIL": "core1-build@users.noreply.github.com",
          "GIT_COMMITTER_NAME": "Core1 build", "GIT_COMMITTER_EMAIL": "core1-build@users.noreply.github.com"}


def template_files(settings):
    """Relative paths of template files, sorted. Skips chart caches."""
    root = settings.gitops_template
    files = []
    for p in sorted(root.rglob("*")):
        rel = p.relative_to(root)
        if p.is_file() and not (set(rel.parts) & SKIP_DIRS) and p.name != ".DS_Store":
            files.append(rel)
    return files


def render(settings, rel):
    """Template file content with the repo URL filled in (bytes)."""
    data = (settings.gitops_template / rel).read_bytes()
    return data.replace(PLACEHOLDER.encode(), settings.gitops_url.encode())


def template_hash(settings):
    h = hashlib.sha256()
    for rel in template_files(settings):
        h.update(str(rel).encode() + b"\0")
        h.update(render(settings, rel) + b"\0")
    return h.hexdigest()


def core1_commit(settings):
    r = run(["git", "-C", settings.root, "rev-parse", "HEAD"], check=False)
    dirty = run(["git", "-C", settings.root, "status", "--porcelain", "--", "gitops"], check=False).stdout.strip()
    return (r.stdout.strip() or "unknown"), bool(dirty)


def write_tree(settings, dest):
    """Replace the Core1-owned paths in DEST with the rendered template, plus the seed marker."""
    for name in OWNED:
        target = dest / name
        if target.is_dir():
            shutil.rmtree(target)
        elif target.exists():
            target.unlink()
    for rel in template_files(settings):
        out = dest / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(render(settings, rel))
        out.chmod((settings.gitops_template / rel).stat().st_mode & 0o777)
    commit, dirty = core1_commit(settings)
    seed = {"template_sha256": template_hash(settings), "core1_commit": commit, "core1_gitops_dirty": dirty}
    (dest / SEED_FILE).parent.mkdir(parents=True, exist_ok=True)
    (dest / SEED_FILE).write_text(json.dumps(seed, indent=2) + "\n")
    return seed


def deployed_hash(gh):
    text = gh.file_text("main", SEED_FILE)
    if not text:
        return None
    try:
        return json.loads(text).get("template_sha256")
    except json.JSONDecodeError:
        return None


def _git(settings, *args, cwd=None, token=None, check=True):
    """git with the token sent as an HTTP header for this one call; nothing is written to git config."""
    pre, secrets = [], []
    if token:
        basic = base64.b64encode(f"x-access-token:{token}".encode()).decode()
        pre = ["-c", f"http.https://github.com/.extraHeader=Authorization: Basic {basic}"]
        secrets = [token, basic]
    env = dict(docker_env(), GIT_TERMINAL_PROMPT="0", **AUTHOR)
    try:
        r = subprocess.run(["git", *pre, "-c", "commit.gpgsign=false", *args], cwd=cwd or settings.gitops_checkout,
                           env=env, capture_output=True, text=True, timeout=180)
    except subprocess.TimeoutExpired as e:
        raise CommandError(f"git {args[0]}: timed out") from e
    if check and r.returncode != 0:
        msg = r.stderr or r.stdout
        for s in secrets:
            msg = msg.replace(s, "***")
        raise CommandError(f"git {args[0]} failed: {msg.strip()[-400:]}")
    return r


def checkout_main(settings, token):
    """Fresh-enough clone of the GitOps repo at origin/main in .work/gitops."""
    dest = settings.gitops_checkout
    if not (dest / ".git").exists():
        shutil.rmtree(dest, ignore_errors=True)
        dest.parent.mkdir(parents=True, exist_ok=True)
        _git(settings, "clone", "-q", settings.gitops_url, str(dest), cwd=settings.work_dir, token=token)
    _git(settings, "fetch", "-q", "--prune", "origin", token=token)
    _git(settings, "checkout", "-q", "-B", "main", "origin/main")
    _git(settings, "clean", "-qfdx")
    return dest


def validate(settings, dest):
    """Run the repo's own CI script locally before pushing."""
    r = run([str(dest / "ci" / "validate.sh")], env=docker_env(settings), check=False, timeout=600)
    if r.returncode != 0:
        raise CommandError("local validation failed:\n" + (r.stdout + r.stderr).strip()[-2000:])


def sync(settings):
    """Bring core1-gitops main in line with the template. Returns (action, main_sha)."""
    token = settings.token("automation")
    gh = GitHub(token, settings.gitops_repo)
    want = template_hash(settings)
    if deployed_hash(gh) == want:
        sha = gh.branch_sha("main")
        checkout_main(settings, token)
        return "unchanged", sha

    dest = checkout_main(settings, token)
    branch = f"core1/platform-{want[:12]}"
    _git(settings, "checkout", "-q", "-B", branch, "origin/main")
    seed = write_tree(settings, dest)
    _git(settings, "add", "-A")
    if not _git(settings, "status", "--porcelain").stdout.strip():
        raise CommandError("template hash differs but the tree is identical; check .core1/seed.json on main")
    log("validating the update locally (ci/validate.sh)")
    validate(settings, dest)
    title = f"Core1 platform update {want[:12]}"
    body = (f"Platform paths owned by Core1 ({', '.join(OWNED)}), from Core1 commit "
            f"`{seed['core1_commit'][:12]}`{' with uncommitted gitops/ changes' if seed['core1_gitops_dirty'] else ''}.\n\n"
            "Opened by `core1 up`. Merged automatically once CI passes.")
    _git(settings, "commit", "-q", "-m", title)
    _git(settings, "push", "-q", "--force", "origin", f"HEAD:refs/heads/{branch}", token=token)
    head = _git(settings, "rev-parse", "HEAD").stdout.strip()
    pr = gh.open_pr_for(branch) or gh.create_pr(branch, title, body)
    log(f"opened PR #{pr['number']}: {pr['html_url']}")

    def waiting(run_):
        state = run_.get("status") if run_ else "not started"
        log(f"waiting for CI on PR #{pr['number']} ({state})")

    ci = gh.wait_for_ci(head, on_wait=waiting)
    if ci.get("conclusion") != "success":
        raise CommandError(f"CI {ci.get('conclusion')} on PR #{pr['number']}: {ci.get('html_url')}. Not merged.")
    sha = gh.merge_pr(pr["number"], head, f"{title} (#{pr['number']})")
    gh.delete_branch(branch)
    log(f"merged PR #{pr['number']} into main at {sha[:7]}")
    checkout_main(settings, token)
    return "merged", sha


def expected_apps(settings):
    """{cluster: number of platform Applications the template defines} plus the root app in mgmt."""
    counts = {c.name: 0 for c in settings.clusters}
    for d in (settings.gitops_template / "platform").glob("*/overlays/*"):
        if d.is_dir() and d.name in counts:
            counts[d.name] += 1
    counts["mgmt"] += 1  # root
    return counts


__all__ = ["sync", "template_hash", "expected_apps", "GitHubError"]

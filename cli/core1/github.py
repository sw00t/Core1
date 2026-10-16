"""Minimal GitHub REST client on urllib. Tokens never appear in messages or on disk."""
import json
import time
import urllib.error
import urllib.parse
import urllib.request

API = "https://api.github.com"


class GitHubError(RuntimeError):
    pass


class GitHub:
    def __init__(self, token, repo):
        if not token:
            raise GitHubError("GitHub token missing; see .env.example")
        self.token = token
        self.repo = repo

    def request(self, method, path, body=None, accept="application/vnd.github+json", ok=(200, 201, 204), parse=True):
        """Returns (status, parsed body or text, headers). Raises GitHubError for other statuses."""
        url = path if path.startswith("http") else f"{API}{path}"
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method, headers={
            "Authorization": f"Bearer {self.token}", "Accept": accept,
            "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "core1-cli",
            **({"Content-Type": "application/json"} if data else {}),
        })
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                status, raw, headers = r.status, r.read(), dict(r.headers)
        except urllib.error.HTTPError as e:
            status, raw, headers = e.code, e.read(), dict(e.headers)
        except (urllib.error.URLError, OSError) as e:
            raise GitHubError(f"{method} {path}: {e}") from e
        text = raw.decode(errors="replace")
        try:
            parsed = json.loads(text) if parse and text and "json" in headers.get("Content-Type", "") else text
        except json.JSONDecodeError:
            parsed = text
        if status not in ok:
            msg = parsed.get("message") if isinstance(parsed, dict) else text[:200]
            raise GitHubError(f"{method} {path}: HTTP {status} {msg}")
        return status, parsed, headers

    def repo_path(self, suffix=""):
        return f"/repos/{self.repo}{suffix}"

    # ---- reads ----

    def file_text(self, ref, path):
        """Contents of PATH at REF, or None if it does not exist."""
        q = urllib.parse.quote(path)
        status, body, _ = self.request("GET", self.repo_path(f"/contents/{q}?ref={ref}"),
                                       accept="application/vnd.github.raw+json", ok=(200, 404), parse=False)
        return None if status == 404 else body

    def branch_sha(self, branch="main"):
        _, body, _ = self.request("GET", self.repo_path(f"/git/ref/heads/{branch}"))
        return body["object"]["sha"]

    def commits_behind(self, sha, branch="main"):
        """How many commits BRANCH has that SHA does not."""
        _, body, _ = self.request("GET", self.repo_path(f"/compare/{sha}...{branch}"))
        return body.get("ahead_by", 0)

    def token_expiry(self):
        """(status of GET repo, expiry header or None)."""
        status, _, headers = self.request("GET", self.repo_path(), ok=(200, 403, 404))
        return status, headers.get("github-authentication-token-expiration") or headers.get("GitHub-Authentication-Token-Expiration")

    def can_read_repo(self, repo):
        status, _, _ = self.request("GET", f"/repos/{repo}", ok=(200, 403, 404))
        return status == 200

    # ---- pull requests ----

    def open_pr_for(self, branch):
        owner = self.repo.split("/")[0]
        _, prs, _ = self.request("GET", self.repo_path(f"/pulls?state=open&head={owner}:{branch}"))
        return prs[0] if prs else None

    def create_pr(self, branch, title, body, base="main"):
        _, pr, _ = self.request("POST", self.repo_path("/pulls"),
                                {"title": title, "head": branch, "base": base, "body": body})
        return pr

    def wait_for_ci(self, sha, workflow="validate", timeout=900, appear_timeout=180, on_wait=None):
        """Wait for the WORKFLOW run on SHA to complete. Returns the run dict. Raises on timeout."""
        start = time.monotonic()
        while True:
            _, body, _ = self.request("GET", self.repo_path(f"/actions/runs?head_sha={sha}&per_page=20"))
            runs = [r for r in body.get("workflow_runs", []) if r.get("name") == workflow]
            if runs and runs[0].get("status") == "completed":
                return runs[0]
            elapsed = time.monotonic() - start
            if not runs and elapsed > appear_timeout:
                raise GitHubError(f"no '{workflow}' run appeared for {sha[:7]} after {appear_timeout}s; are Actions enabled?")
            if elapsed > timeout:
                raise GitHubError(f"'{workflow}' run for {sha[:7]} not finished after {timeout}s")
            if on_wait:
                on_wait(runs[0] if runs else None)
            time.sleep(10)

    def merge_pr(self, number, sha, title):
        _, body, _ = self.request("PUT", self.repo_path(f"/pulls/{number}/merge"),
                                  {"merge_method": "squash", "sha": sha, "commit_title": title})
        return body["sha"]

    def delete_branch(self, branch):
        self.request("DELETE", self.repo_path(f"/git/refs/heads/{branch}"), ok=(204, 404, 422))

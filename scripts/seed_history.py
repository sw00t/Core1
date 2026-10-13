#!/usr/bin/env python3
"""Build the config repo's git history from the template (which holds the baseline state).
Applies the seed edits in reverse to produce the initial commit, then replays them forward,
each with its author and a backdated timestamp. Tags the final commit 'baseline'."""
import json, os, subprocess, sys, time

repo, seed_file = sys.argv[1], sys.argv[2]
seed = json.load(open(seed_file))

def git(*args, env=None):
    e = dict(os.environ); e.update(env or {})
    subprocess.run(["git", "-c", "commit.gpgsign=false", "-c", "init.defaultBranch=main"] + list(args), cwd=repo, check=True, env=e,
                   stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)

def edit(path, old, new):
    p = os.path.join(repo, path)
    s = open(p).read()
    if s.count(old) != 1:
        raise SystemExit(f"seed edit for {path}: expected exactly one match for {old!r}, found {s.count(old)}")
    open(p, "w").write(s.replace(old, new))

def commit(message, author, days_ago):
    ts = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(time.time() - days_ago * 86400 - 3600 * (days_ago % 5)))
    name, email = author.rsplit(" <", 1); email = email.rstrip(">")
    env = {"GIT_AUTHOR_NAME": name, "GIT_AUTHOR_EMAIL": email, "GIT_AUTHOR_DATE": ts,
           "GIT_COMMITTER_NAME": name, "GIT_COMMITTER_EMAIL": email, "GIT_COMMITTER_DATE": ts}
    git("add", "-A")
    git("commit", "-q", "-m", message, env=env)

git("init", "-q")
# walk back to the initial state
for e in reversed(seed["edits"]):
    for c in reversed(e["changes"]):
        edit(c["file"], c["new"], c["old"])
commit(seed["initial"]["message"], seed["initial"]["author"], seed["initial"]["days_ago"])
# replay forward
for e in seed["edits"]:
    for c in e["changes"]:
        edit(c["file"], c["old"], c["new"])
    commit(e["message"], e["author"], e["days_ago"])
git("tag", "-f", "baseline")
# sanity: the working tree must equal the template now
diff = subprocess.run(["diff", "-r", "-x", ".git", repo, os.path.join(os.path.dirname(seed_file), "..", "config-repo-template")],
                      capture_output=True, text=True)
if diff.returncode != 0:
    raise SystemExit("seeded repo does not match the template after replay:\n" + diff.stdout)
print("seeded %d commits, tagged baseline" % (len(seed["edits"]) + 1))

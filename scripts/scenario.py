#!/usr/bin/env python3
"""Inject and clear fault scenarios.

  scenario.py list
  scenario.py inject N        commit + deploy a change (kinds: config-change) or flip a runtime fault
  scenario.py expected N      print the answer file for N (for the eval harness, not for the agent)
  scenario.py clear-runtime-faults
  scenario.py active          show the currently injected scenario, if any

Reads .work/endpoints.env for paths and URLs. Standard library only.
"""
import json, os, subprocess, sys, time, urllib.request

try:
    sys.stdout.reconfigure(line_buffering=True)  # progress shows up in log files as it happens
except AttributeError:
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCENARIOS = json.load(open(os.path.join(ROOT, "scenarios", "scenarios.json")))
ACTIVE_FILE = os.path.join(ROOT, ".work", "scenario-active.json")


def endpoints():
    p = os.path.join(ROOT, ".work", "endpoints.env")
    if not os.path.exists(p):
        raise SystemExit("endpoints file missing; run: make up")
    d = {}
    for line in open(p):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1); d[k] = v
    return d


def kubectl(E, *args, check=True, capture=True):
    cmd = [os.path.join(ROOT, ".bin", "kubectl")] + list(args)
    env = dict(os.environ, KUBECONFIG=E["CORE1_KUBECONFIG_ADMIN"])
    return subprocess.run(cmd, env=env, check=check, capture_output=capture, text=True)


def git(E, *args, env=None):
    e = dict(os.environ); e.update(env or {})
    return subprocess.run(["git", "-c", "commit.gpgsign=false"] + list(args), cwd=E["CORE1_CONFIG_REPO"], check=True,
                          capture_output=True, text=True, env=e)


def find(n):
    for s in SCENARIOS:
        if str(s["id"]) == str(n) or s["name"] == str(n):
            return s
    raise SystemExit(f"no scenario {n}; try: scenario.py list")


def cmd_list():
    for s in SCENARIOS:
        print(f"  {s['id']}  {s['name']:<28} {s['kind']:<14} {s['title']}")


def set_inventory_fault(E, latency_ms, error_rate):
    ns = E["CORE1_NS_APP"]
    pods = kubectl(E, "-n", ns, "get", "pods", "-l", "app.kubernetes.io/name=inventory", "-o", "jsonpath={.items[*].metadata.name}").stdout.split()
    if not pods:
        print("  no inventory pods found")
        return 0
    body = json.dumps({"latency_ms": latency_ms, "error_rate": error_rate})
    code = ("import json,urllib.request as u; r=u.Request('http://127.0.0.1:8080/admin/fault', data=%r, "
            "headers={'Content-Type':'application/json'}); print(u.urlopen(r, timeout=5).read().decode())") % body.encode()
    n = 0
    for pod in pods:
        r = kubectl(E, "-n", ns, "exec", pod, "--", "python", "-c", code, check=False)
        if r.returncode == 0:
            n += 1
        else:
            print(f"  warning: could not set fault on {pod}: {r.stderr.strip()[:120]}")
    return n


def deploy(E):
    env = dict(os.environ, KUBECTL=os.path.join(ROOT, ".bin", "kubectl"), KUBECONFIG=E["CORE1_KUBECONFIG_ADMIN"],
               DEPLOY_NAMESPACE=E["CORE1_NS_APP"], LOKI_PUSH_URL=E["CORE1_LOKI_URL"] + "/loki/api/v1/push")
    subprocess.run([os.path.join(E["CORE1_CONFIG_REPO"], "deploy.sh")], env=env, check=True)


def cmd_inject(n):
    E = endpoints()
    s = find(n)
    if os.path.exists(ACTIVE_FILE):
        a = json.load(open(ACTIVE_FILE))
        raise SystemExit(f"scenario {a['id']} ({a['name']}) is already active; run: make reset")
    repo = E["CORE1_CONFIG_REPO"]
    print(f"== scenario {s['id']}: {s['title']}")
    record = {"id": s["id"], "name": s["name"], "kind": s["kind"], "injected_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    if s["kind"] == "config-change":
        st = git(E, "status", "--porcelain").stdout.strip()
        if st:
            raise SystemExit("config repo has uncommitted changes; run: make reset")
        git(E, "checkout", "-q", "main")
        for e in s["edits"]:
            p = os.path.join(repo, e["file"])
            txt = open(p).read()
            if txt.count(e["find"]) != 1:
                raise SystemExit(f"edit target not found exactly once in {e['file']}: {e['find']!r}")
            open(p, "w").write(txt.replace(e["find"], e["replace"]))
        name, email = s["commit"]["author"].rsplit(" <", 1); email = email.rstrip(">")
        env = {"GIT_AUTHOR_NAME": name, "GIT_AUTHOR_EMAIL": email, "GIT_COMMITTER_NAME": name, "GIT_COMMITTER_EMAIL": email}
        git(E, "add", "-A")
        git(E, "commit", "-q", "-m", s["commit"]["message"], env=env)
        sha = git(E, "rev-parse", "--short", "HEAD").stdout.strip()
        record["commit"] = sha
        print(f"   committed {sha} as {name}: {s['commit']['message'].splitlines()[0]}")
        deploy(E)
    elif s["kind"] == "runtime-fault":
        f = s["fault"]
        n_pods = set_inventory_fault(E, f["latency_ms"], f["error_rate"])
        record["fault"] = f
        print(f"   runtime fault set on {n_pods} {f['target']} pod(s): latency {f['latency_ms']}ms, error rate {f['error_rate']}")
    else:
        raise SystemExit(f"unknown scenario kind {s['kind']}")
    os.makedirs(os.path.dirname(ACTIVE_FILE), exist_ok=True)
    json.dump(record, open(ACTIVE_FILE, "w"), indent=2)
    exp = s["expected"]
    print(f"   expect one of {exp['alerts_any_of']} within ~{exp['detect_within_s']}s. Answer file: scripts/scenario.py expected {s['id']}")
    print("   restore with: make reset")


def cmd_clear_runtime_faults():
    E = endpoints()
    n = set_inventory_fault(E, 0, 0.0)
    if os.path.exists(ACTIVE_FILE):
        os.remove(ACTIVE_FILE)
    print(f"  runtime faults cleared on {n} pod(s); active scenario marker removed")


def cmd_expected(n):
    s = find(n)
    print(json.dumps({"id": s["id"], "name": s["name"], "title": s["title"], "kind": s["kind"], "expected": s["expected"]}, indent=2))


def cmd_active():
    if os.path.exists(ACTIVE_FILE):
        print(open(ACTIVE_FILE).read())
    else:
        print("  no scenario active")


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print(__doc__); sys.exit(0)
    c = args[0]
    if c == "list": cmd_list()
    elif c == "inject": cmd_inject(args[1])
    elif c == "expected": cmd_expected(args[1])
    elif c == "clear-runtime-faults": cmd_clear_runtime_faults()
    elif c == "active": cmd_active()
    else:
        print(__doc__); sys.exit(2)

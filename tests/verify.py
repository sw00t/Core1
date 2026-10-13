#!/usr/bin/env python3
"""Acceptance tests for the Core1 base. Standard library only.

  verify.py              quick checks (cluster, metrics, logs, baseline traffic, alert wiring, read-only identity)
  verify.py --scenarios  plus every scenario: inject, wait for the expected alert, reset, wait for green

Writes reports/verify-<timestamp>.md and .json. Exit code 1 if any check failed.
"""
import argparse, json, os, subprocess, sys, time, urllib.parse, urllib.request, base64

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KUBECTL = os.path.join(ROOT, ".bin", "kubectl")
RESULTS = []


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


E = endpoints()
NS_APP, NS_OBS, NS_SYS = E["CORE1_NS_APP"], E["CORE1_NS_OBS"], E["CORE1_NS_SYS"]


def http(url, timeout=10, headers=None, method="GET", data=None):
    req = urllib.request.Request(url, headers=headers or {}, method=method, data=data)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, r.read().decode()


def http_json(url, **kw):
    s, b = http(url, **kw)
    return json.loads(b)


def promql(q, t=None):
    url = E["CORE1_PROMETHEUS_URL"] + "/api/v1/query?" + urllib.parse.urlencode({"query": q})
    d = http_json(url)
    return d["data"]["result"]


def kubectl(*args, kubeconfig=None, check=True):
    env = dict(os.environ, KUBECONFIG=kubeconfig or E["CORE1_KUBECONFIG_ADMIN"])
    return subprocess.run([KUBECTL] + list(args), env=env, capture_output=True, text=True, check=check)


def check(name, fn):
    t0 = time.time()
    try:
        ok, detail = fn()
    except Exception as exc:  # noqa: BLE001
        ok, detail = False, f"exception: {exc.__class__.__name__}: {str(exc)[:300]}"
    RESULTS.append({"name": name, "ok": bool(ok), "detail": detail, "seconds": round(time.time() - t0, 1)})
    print(f"  {'ok  ' if ok else 'FAIL'}  {name}  ({round(time.time() - t0, 1)}s)  {detail}")
    return ok


def wait_until(fn, timeout, interval=10):
    start = time.time()
    last = None
    while time.time() - start < timeout:
        ok, last = fn()
        if ok:
            return True, last, round(time.time() - start)
        time.sleep(interval)
    return False, last, round(time.time() - start)


# ---------------------------------------------------------------- checks
def c_nodes():
    r = kubectl("get", "nodes", "-o", "json")
    nodes = json.loads(r.stdout)["items"]
    ready = [n["metadata"]["name"] for n in nodes if any(c["type"] == "Ready" and c["status"] == "True" for c in n["status"]["conditions"])]
    return len(ready) == len(nodes) and nodes, f"{len(ready)}/{len(nodes)} nodes Ready"


def c_pods():
    bad = []
    total = 0
    for ns in (NS_APP, NS_SYS, NS_OBS):
        pods = json.loads(kubectl("-n", ns, "get", "pods", "-o", "json").stdout)["items"]
        for p in pods:
            total += 1
            phase = p["status"].get("phase")
            if phase == "Succeeded":
                continue
            ready = all(cs.get("ready") for cs in p["status"].get("containerStatuses", [])) and p["status"].get("containerStatuses")
            if phase != "Running" or not ready:
                bad.append(f"{ns}/{p['metadata']['name']}:{phase}")
    return not bad, f"{total - len(bad)}/{total} pods Running and Ready" + (f"; not ready: {', '.join(bad[:6])}" if bad else "")


def c_prom_targets():
    d = http_json(E["CORE1_PROMETHEUS_URL"] + "/api/v1/targets?state=active")
    up = {}
    for t in d["data"]["activeTargets"]:
        lbl = t.get("labels", {})
        if lbl.get("namespace") in (NS_APP, NS_SYS) and lbl.get("service"):
            up.setdefault(lbl["service"], []).append(t.get("health"))
    want = {"gateway": 2, "orders": 2, "inventory": 2, "loadgen": 1, "alert-sink": 1}
    missing = [f"{s} ({up.get(s, []).count('up')}/{n} up)" for s, n in want.items() if up.get(s, []).count("up") < n]
    return not missing, "all app targets up" if not missing else "short: " + ", ".join(missing)


def c_loki_logs():
    missing = []
    end = time.time_ns(); start = end - 10 * 60 * 10**9
    for app in ("gateway", "orders", "inventory"):
        q = urllib.parse.urlencode({"query": '{namespace="%s", app="%s"}' % (NS_APP, app), "limit": "5", "start": str(start), "end": str(end)})
        d = http_json(E["CORE1_LOKI_URL"] + "/loki/api/v1/query_range?" + q, timeout=20)
        n = sum(len(s["values"]) for s in d["data"]["result"])
        if n == 0:
            missing.append(app)
    q = urllib.parse.urlencode({"query": '{job="deploy-events"}', "limit": "5", "start": str(end - 24 * 3600 * 10**9), "end": str(end)})
    d = http_json(E["CORE1_LOKI_URL"] + "/loki/api/v1/query_range?" + q, timeout=20)
    ndeploy = sum(len(s["values"]) for s in d["data"]["result"])
    if ndeploy == 0:
        missing.append("deploy-events")
    return not missing, "logs present for gateway, orders, inventory and deploy-events" if not missing else "no recent logs for: " + ", ".join(missing)


def c_baseline_traffic():
    rate = promql('sum(rate(http_requests_total{namespace="%s", service="gateway"}[2m]))' % NS_APP)
    rps = float(rate[0]["value"][1]) if rate else 0.0
    err = promql('sum(rate(http_requests_total{namespace="%s", status=~"5.."}[2m])) / sum(rate(http_requests_total{namespace="%s"}[2m]))' % (NS_APP, NS_APP))
    ratio = float(err[0]["value"][1]) if err and err[0]["value"][1] != "NaN" else 0.0
    p95 = promql('histogram_quantile(0.95, sum by (le) (rate(http_request_duration_seconds_bucket{namespace="%s", service="gateway"}[2m])))' % NS_APP)
    p95v = float(p95[0]["value"][1]) if p95 and p95[0]["value"][1] != "NaN" else -1
    ok = rps >= 5 and ratio < 0.01 and 0 <= p95v < 0.5
    return ok, f"gateway {rps:.1f} rps, 5xx ratio {ratio*100:.2f}%, p95 {p95v*1000:.0f}ms"


def c_no_lab_alerts():
    a = http_json(E["CORE1_ALERTMANAGER_URL"] + '/api/v2/alerts?active=true&filter=lab%3D%22core1%22')
    names = sorted({x["labels"]["alertname"] for x in a})
    return not names, "no lab alerts active" if not names else "active: " + ", ".join(names)


def c_alert_wiring():
    s = http_json(E["CORE1_ALERTMANAGER_URL"] + "/api/v2/status")
    cfg = s.get("config", {}).get("original", "")
    hooked = E["CORE1_ALERT_WEBHOOK_URL"] in cfg
    st, _ = http(E["CORE1_ALERT_SINK_URL"] + "/healthz")
    return hooked and st == 200, f"webhook {'configured' if hooked else 'MISSING'} in Alertmanager; alert-sink healthz {st}"


def c_grafana():
    h = http_json(E["CORE1_GRAFANA_URL"] + "/api/health")
    auth = base64.b64encode(f"{E['CORE1_GRAFANA_USER']}:{E['CORE1_GRAFANA_PASSWORD']}".encode()).decode()
    ds = http_json(E["CORE1_GRAFANA_URL"] + "/api/datasources", headers={"Authorization": "Basic " + auth})
    types = sorted({d["type"] for d in ds})
    ok = h.get("database") == "ok" and "prometheus" in types and "loki" in types
    return ok, f"health {h.get('database')}, datasources {types}"


def c_readonly_identity():
    kc = E["CORE1_KUBECONFIG_AGENT"]
    def can(verb, res, ns=NS_APP):
        r = kubectl("auth", "can-i", verb, res, "-n", ns, kubeconfig=kc, check=False)
        return r.stdout.strip() == "yes"
    must_yes = [("get", "pods"), ("list", "deployments"), ("get", "pods/log"), ("list", "events"), ("get", "configmaps")]
    must_no = [("get", "secrets"), ("create", "pods"), ("patch", "deployments"), ("delete", "pods"), ("create", "pods/exec")]
    wrong = [f"{v} {r} should be yes" for v, r in must_yes if not can(v, r)] + [f"{v} {r} should be no" for v, r in must_no if can(v, r)]
    r = kubectl("-n", NS_APP, "annotate", "deployment/gateway", "verify=1", kubeconfig=kc, check=False)
    if r.returncode == 0:
        wrong.append("annotate deployment succeeded (should be forbidden)")
        kubectl("-n", NS_APP, "annotate", "deployment/gateway", "verify-")
    return not wrong, "read-only identity behaves" if not wrong else "; ".join(wrong)


def c_disk():
    r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "disk_check.py"), "--json"], capture_output=True, text=True)
    d = json.loads(r.stdout)
    gb = d["total_bytes"] / 1024**3
    return not d["over_ceiling"] and not d["host_low"], f"lab uses {gb:.2f} GB of {d['ceiling_gb']:.0f} GB ceiling; host free {d['host_free_bytes']/1024**3:.1f} GB"


# ---------------------------------------------------------------- scenarios
def scenarios():
    return json.load(open(os.path.join(ROOT, "scenarios", "scenarios.json")))


def active_lab_alerts():
    a = http_json(E["CORE1_ALERTMANAGER_URL"] + '/api/v2/alerts?active=true&filter=lab%3D%22core1%22')
    return sorted({x["labels"]["alertname"] for x in a})


def run_scenario(s):
    exp = s["expected"]
    def inject():
        r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "scenario.py"), "inject", str(s["id"])], capture_output=True, text=True)
        if r.returncode != 0:
            return False, "inject failed: " + (r.stderr or r.stdout)[-300:]
        http(E["CORE1_ALERT_SINK_URL"] + "/alerts", method="DELETE")
        return True, "injected"
    if not check(f"scenario {s['id']} inject ({s['name']})", inject):
        return
    def alert_seen():
        names = active_lab_alerts()
        return any(n in names for n in exp["alerts_any_of"]), names
    ok, names, secs = wait_until(alert_seen, exp["detect_within_s"], interval=10)
    check(f"scenario {s['id']} expected alert", lambda: (ok, f"after {secs}s active={names}; expected any of {exp['alerts_any_of']}"))
    def sink_got_it():
        got = http_json(E["CORE1_ALERT_SINK_URL"] + "/alerts?limit=50")
        seen = {n for e in got for n in e.get("alertnames", [])}
        return any(n in seen for n in exp["alerts_any_of"]), sorted(seen)
    ok2, seen, secs2 = wait_until(sink_got_it, 150, interval=10)
    check(f"scenario {s['id']} webhook delivered", lambda: (ok2, f"after {secs2}s sink saw {seen}"))
    def reset():
        r = subprocess.run([os.path.join(ROOT, "scripts", "reset.sh")], capture_output=True, text=True)
        return r.returncode == 0, ("reset to baseline and green" if r.returncode == 0 else "reset failed: " + (r.stderr or r.stdout)[-400:])
    check(f"scenario {s['id']} reset", reset)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenarios", action="store_true")
    ap.add_argument("--only", help="comma-separated scenario ids")
    a = ap.parse_args()
    t0 = time.time()
    print("== Core1 verify")
    check("nodes ready", c_nodes)
    check("pods running and ready", c_pods)
    check("prometheus scraping app targets", c_prom_targets)
    check("loki has logs and deploy events", c_loki_logs)
    check("baseline traffic healthy", c_baseline_traffic)
    check("no lab alerts active", c_no_lab_alerts)
    check("alertmanager webhook wired", c_alert_wiring)
    check("grafana up with prometheus and loki", c_grafana)
    check("read-only identity", c_readonly_identity)
    check("disk within ceiling", c_disk)
    if a.scenarios:
        ids = {int(x) for x in a.only.split(",")} if a.only else None
        for s in scenarios():
            if ids is None or s["id"] in ids:
                run_scenario(s)
        check("disk within ceiling (after scenarios)", c_disk)
    passed = sum(1 for r in RESULTS if r["ok"]); failed = len(RESULTS) - passed
    ts = time.strftime("%Y%m%d-%H%M%S")
    os.makedirs(os.path.join(ROOT, "reports"), exist_ok=True)
    md = [f"# Core1 verify report {ts}", "", f"Result: {'PASS' if failed == 0 else 'FAIL'}: {passed} passed, {failed} failed, {round(time.time()-t0)}s total", "",
          "| check | result | seconds | detail |", "|---|---|---|---|"]
    for r in RESULTS:
        md.append(f"| {r['name']} | {'ok' if r['ok'] else 'FAIL'} | {r['seconds']} | {r['detail'].replace('|', '/')} |")
    open(os.path.join(ROOT, "reports", f"verify-{ts}.md"), "w").write("\n".join(md) + "\n")
    json.dump({"timestamp": ts, "passed": passed, "failed": failed, "results": RESULTS}, open(os.path.join(ROOT, "reports", f"verify-{ts}.json"), "w"), indent=2)
    print(f"== {'PASS' if failed == 0 else 'FAIL'}: {passed} passed, {failed} failed. Report: reports/verify-{ts}.md")
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()

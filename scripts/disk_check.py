#!/usr/bin/env python3
"""Measure what this lab uses on disk and enforce the ceiling.

Counts: the repo folder, Docker volumes mounted by the k3d node containers,
the node/loadbalancer containers' writable layers, and images the lab pulled
or built on the host (core1.local/*, rancher/k3s, k3d tooling).
Also checks free space on the host volume. Standard library only.

Exit codes: 0 ok, 2 over ceiling / under host minimum, 3 docker unavailable.
"""
import argparse, json, os, re, shutil, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CEILING_GB = float(os.environ.get("DISK_CEILING_GB", "20"))
HOST_MIN_GB = float(os.environ.get("HOST_FREE_MIN_GB", "6"))
CLUSTER = os.environ.get("CLUSTER_NAME", "core1")
GB = 1024 ** 3

def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=120)

def human_to_bytes(s):
    s = (s or "").strip()
    m = re.match(r"([0-9.]+)\s*([kKMGT]?i?B)?", s)
    if not m:
        return 0
    n = float(m.group(1)); u = (m.group(2) or "B").upper()
    mult = {"B": 1, "KB": 1e3, "KIB": 1024, "MB": 1e6, "MIB": 1024**2,
            "GB": 1e9, "GIB": 1024**3, "TB": 1e12, "TIB": 1024**4}
    return int(n * mult.get(u, 1))

def du(path):
    total = 0
    for dp, dn, fn in os.walk(path):
        for f in fn:
            try:
                total += os.lstat(os.path.join(dp, f)).st_size
            except OSError:
                pass
    return total

def docker_usage():
    r = run(["docker", "ps", "-a", "--filter", f"name=k3d-{CLUSTER}", "--format", "{{.Names}}"])
    if r.returncode != 0:
        return None
    names = [n for n in r.stdout.split() if n]
    vol_names = set()
    if names:
        ins = run(["docker", "inspect"] + names)
        if ins.returncode == 0:
            for c in json.loads(ins.stdout):
                for m in c.get("Mounts", []):
                    if m.get("Type") == "volume" and m.get("Name"):
                        vol_names.add(m["Name"])
    df = run(["docker", "system", "df", "-v", "--format", "{{json .}}"])
    if df.returncode != 0:
        return {"containers": 0, "volumes": 0, "images": 0, "detail": "docker system df unavailable"}
    try:
        d = json.loads(df.stdout)
    except json.JSONDecodeError:
        # some docker versions print one json object per line
        d = {}
        for line in df.stdout.splitlines():
            try:
                d.update(json.loads(line))
            except json.JSONDecodeError:
                pass
    containers = sum(human_to_bytes((c.get("Size") or "").split(" ")[0])
                     for c in d.get("Containers", []) if (c.get("Names") or "").startswith(f"k3d-{CLUSTER}"))
    volumes = sum(human_to_bytes(v.get("Size")) for v in d.get("Volumes", [])
                  if v.get("Name") in vol_names or (v.get("Name") or "").startswith(f"k3d-{CLUSTER}"))
    images = 0
    for im in d.get("Images", []):
        repo = im.get("Repository") or ""
        if repo.startswith("core1.local/") or repo.startswith("rancher/k3s") or repo.startswith("ghcr.io/k3d-io/"):
            images += human_to_bytes(im.get("UniqueSize") or im.get("Size"))
    return {"containers": containers, "volumes": volumes, "images": images, "detail": f"{len(names)} containers, {len(vol_names)} volumes"}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", action="store_true", help="print a report (always)")
    ap.add_argument("--enforce", action="store_true", help="exit 2 if over ceiling")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    repo = du(ROOT)
    dk = docker_usage()
    usage = {"repo_bytes": repo}
    if dk is None:
        usage["docker"] = "unavailable"
        total = repo
    else:
        usage["docker"] = dk
        total = repo + dk["containers"] + dk["volumes"] + dk["images"]
    st = shutil.disk_usage(ROOT)
    usage["total_bytes"] = total
    usage["host_free_bytes"] = st.free
    usage["ceiling_gb"] = CEILING_GB
    usage["host_free_min_gb"] = HOST_MIN_GB
    over = total > CEILING_GB * GB
    low = st.free < HOST_MIN_GB * GB
    usage["over_ceiling"] = over
    usage["host_low"] = low

    if a.json:
        print(json.dumps(usage, indent=2))
    else:
        docker_gb = "n/a" if dk is None else "%.2f" % ((dk["containers"] + dk["volumes"] + dk["images"]) / GB)
        print("  disk  lab usage %.2f GB of %.0f GB ceiling (repo %.2f, docker %s GB); host free %.1f GB (min %.0f)"
              % (total / GB, CEILING_GB, repo / GB, docker_gb, st.free / GB, HOST_MIN_GB))
        if dk is None:
            print("  note  docker not reachable; only the repo folder was measured")
    if over or low:
        msg = "lab usage over the disk ceiling" if over else "host free space below minimum"
        print(f"  {'FAIL' if a.enforce else 'WARN'}  {msg}", file=sys.stderr)
        if a.enforce or a.report:
            sys.exit(2)
    sys.exit(0)

if __name__ == "__main__":
    main()

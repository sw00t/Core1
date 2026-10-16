"""core1: one entrypoint for the Core1 lab (DESIGN.md section 12)."""
import time
from enum import Enum
from typing import Optional

import typer

from . import argocd, clusters, dns, gitops
from .config import Settings
from .doctor import run_doctor
from .endpoints import write_endpoints
from .github import GitHub, GitHubError
from .nuke import nuke as do_nuke
from .shell import CommandError, log
from .tools import ensure_tools, require_tools

app = typer.Typer(add_completion=False, no_args_is_help=True,
                  help="Core1: a reusable enterprise lab. See DESIGN.md.")
pack_app = typer.Typer(no_args_is_help=True, help="Vertical packs (phase 6).")
scenario_app = typer.Typer(no_args_is_help=True, help="Scenarios and fault injection (phase 7).")
reset_app = typer.Typer(no_args_is_help=True, help="Reset one layer.")
test_app = typer.Typer(no_args_is_help=True, help="Tests.")
app.add_typer(pack_app, name="pack")
app.add_typer(scenario_app, name="scenario")
app.add_typer(reset_app, name="reset")
app.add_typer(test_app, name="test")


class Profile(str, Enum):
    full = "full"
    lite = "lite"


def settings():
    return Settings()


def not_yet(what, phase):
    typer.echo(f"core1 {what}: arrives in phase {phase} (DESIGN.md section 13)", err=True)
    raise typer.Exit(2)


def print_results(results):
    for name, ok, detail in results:
        typer.echo(f"  {'ok  ' if ok else 'FAIL'}  {name}" + (f"  ({detail})" if detail else ""))
    return all(ok for _, ok, _ in results)


def guarded(fn):
    """Turn CommandError into a clean message and exit 1."""
    try:
        return fn()
    except (CommandError, GitHubError) as e:
        typer.echo(f"core1: {e}", err=True)
        raise typer.Exit(1)


@app.command()
def doctor():
    """Host checks: Docker Desktop resources, ports, tools."""
    if not run_doctor(settings()):
        typer.echo("core1 doctor: problems found", err=True)
        raise typer.Exit(1)


@app.command()
def up(profile: Profile = typer.Option(Profile.full, help="full (default) or lite")):
    """Idempotent bring-up: tools, network, registry, three clusters, green gate."""
    if profile is Profile.lite:
        not_yet("up --profile lite", "8 or later (fallback profile)")
    s = settings()

    def _up():
        start = time.monotonic()
        if not run_doctor(s):
            typer.echo("core1 up: doctor found problems; fix them first", err=True)
            raise typer.Exit(1)
        ensure_tools(s)
        clusters.ensure_network(s)
        clusters.ensure_registry(s)
        states = clusters.cluster_states(s)
        for c in s.clusters:
            clusters.ensure_cluster(s, c, states)
        write_endpoints(s)
        log("waiting for the clusters")
        if not print_results(clusters.wait_green(s, timeout=300)):
            typer.echo("core1 up: clusters not green after 300s; see above, then ./core1 status", err=True)
            raise typer.Exit(1)

        for c in s.clusters:
            dns.ensure_dns(s, c)
        action, head = gitops.sync(s)
        log(f"core1-gitops main at {head[:7]} ({action})")
        checkout = s.gitops_checkout
        if not argocd.installed(s):
            argocd.install(s, checkout)
        argocd.register_clusters(s)
        argocd.ensure_repo_secret(s)
        argocd.apply_root(s, checkout)
        argocd.refresh_all(s)

        log("waiting for Argo CD to sync every cluster to main")
        rows, head = wait_argo(s, timeout=900)
        typer.echo(argocd.format_rows(rows, head))
        if not all(r["ok"] for r in rows):
            typer.echo("core1 up: Argo CD not synced after 900s; see ./core1 status", err=True)
            raise typer.Exit(1)
        log(f"green in {time.monotonic() - start:.0f}s. Kubeconfigs in .kube/, endpoints in .work/endpoints.json")

    guarded(_up)


def argo_view(s):
    """(rows, head) for the Argo CD glance view. Uses the read-only token for main HEAD."""
    gh = None
    head = None
    try:
        gh = GitHub(s.token("argocd"), s.gitops_repo)
        head = gh.branch_sha("main")
    except GitHubError as e:
        typer.echo(f"  note  main HEAD unknown: {e}", err=True)
    cache = {}

    def behind(rev):
        if rev not in cache:
            try:
                cache[rev] = gh.commits_behind(rev) if gh else 0
            except GitHubError:
                cache[rev] = 0
        return cache[rev]

    rows = argocd.summarize(argocd.applications(s), gitops.expected_apps(s), head, behind)
    return rows, head


def wait_argo(s, timeout):
    deadline = time.monotonic() + timeout
    last = None
    while True:
        rows, head = argo_view(s)
        if all(r["ok"] for r in rows) or time.monotonic() >= deadline:
            return rows, head
        summary = ", ".join(f"{r['cluster']} {r['synced']}/{r['expected']} {r['position']}" for r in rows)
        if summary != last:
            log(f"Argo CD: {summary}")
            last = summary
        time.sleep(10)


@app.command()
def status(watch: bool = typer.Option(False, "--watch", "-w", help="Refresh the Argo CD view every 5 s until Ctrl-C")):
    """Clusters, nodes, system pods, registry, and Argo CD sync against main."""
    s = settings()

    def _status():
        require_tools(s)
        if watch:
            try:
                while True:
                    rows, head = argo_view(s)
                    typer.echo("\033[2J\033[H" + time.strftime("%H:%M:%S  ") + argocd.format_rows(rows, head)
                               + "\n\n(Ctrl-C to stop)")
                    time.sleep(5)
            except KeyboardInterrupt:
                return
        states = clusters.cluster_states(s)
        for c in s.clusters:
            st = states.get(c.name)
            if st is None:
                typer.echo(f"  {c.name:6} absent")
            else:
                (sr, st_), (ar, at) = st["servers"], st["agents"]
                typer.echo(f"  {c.name:6} servers {sr}/{st_} agents {ar}/{at}  API 127.0.0.1:{c.api_port}  "
                           f"HTTP {c.http_port}  HTTPS {c.https_port}")
        ok = print_results(clusters.check_all(s))
        if argocd.installed(s):
            rows, head = argo_view(s)
            typer.echo(argocd.format_rows(rows, head))
            ok = ok and all(r["ok"] for r in rows)
        else:
            typer.echo("Argo CD  not installed yet (./core1 up)")
        if not ok:
            raise typer.Exit(1)

    guarded(_status)


@app.command()
def endpoints():
    """Regenerate .work/endpoints.json and .work/endpoints.env."""
    write_endpoints(settings())


@app.command()
def nuke(all_: bool = typer.Option(False, "--all", help="Also remove .bin, .venv and pulled images"),
         yes: bool = typer.Option(False, "--yes", "-y", help="Do not ask for confirmation")):
    """Delete the clusters, registry, network and local state."""
    s = settings()
    what = "clusters mgmt, stage, prod, the registry, network core1, .kube/*.yaml, .work"
    if all_:
        what += ", .bin, .venv and Core1's images"
    if not yes and not typer.confirm(f"Delete {what}?"):
        raise typer.Exit(1)

    def _nuke():
        left = do_nuke(s, everything=all_)
        if left:
            typer.echo("core1 nuke: still present:\n" + "\n".join(f"  {x}" for x in left), err=True)
            raise typer.Exit(1)
        log("nothing left behind")

    guarded(_nuke)


@pack_app.command("list")
def pack_list():
    not_yet("pack list", 6)


@pack_app.command("install")
def pack_install(pack_id: str):
    not_yet("pack install", 6)


@pack_app.command("remove")
def pack_remove(pack_id: str):
    not_yet("pack remove", 6)


@pack_app.command("swap")
def pack_swap(pack_id: str):
    not_yet("pack swap", 6)


@scenario_app.command("list")
def scenario_list():
    not_yet("scenario list", 7)


@scenario_app.command("run")
def scenario_run(scenario_id: str, noise: Optional[str] = typer.Option(None, help="low, med or high")):
    not_yet("scenario run", 7)


@reset_app.command("scenario")
def reset_scenario():
    not_yet("reset scenario", 7)


@reset_app.command("pack")
def reset_pack():
    not_yet("reset pack", 6)


@reset_app.command("app")
def reset_app_layer():
    not_yet("reset app", 5)


@reset_app.command("platform")
def reset_platform():
    not_yet("reset platform", 2)


@test_app.command("smoke")
def test_smoke():
    """Green checks plus an image pull through the registry in every cluster."""
    s = settings()

    def _smoke():
        require_tools(s)
        clusters.require_kubeconfigs(s)
        ok = print_results(clusters.check_all(s))
        ok = print_results(clusters.smoke_pull(s)) and ok
        if not ok:
            raise typer.Exit(1)
        log("smoke passed")

    guarded(_smoke)


@test_app.command("pack-seam")
def test_pack_seam():
    not_yet("test pack-seam", 6)


@test_app.command("all")
def test_all():
    not_yet("test all", 8)

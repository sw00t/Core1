"""Docker engine queries."""
import json

from .shell import docker_env, run


def docker(settings, *args, check=True, timeout=120):
    return run(["docker", *args], env=docker_env(settings), check=check, timeout=timeout)


def info(settings):
    """docker info as a dict, or None when the engine is unreachable."""
    r = docker(settings, "info", "--format", "{{json .}}", check=False, timeout=30)
    if r.returncode != 0:
        return None
    try:
        return json.loads(r.stdout)
    except json.JSONDecodeError:
        return None


def lines(settings, *args):
    r = docker(settings, *args, check=False)
    return [l for l in r.stdout.splitlines() if l.strip()] if r.returncode == 0 else []


def network_exists(settings, name):
    return docker(settings, "network", "inspect", name, check=False).returncode == 0


def container_running(settings, name):
    r = docker(settings, "inspect", "-f", "{{.State.Running}}", name, check=False)
    return r.returncode == 0 and r.stdout.strip() == "true"


def container_exists(settings, name):
    return docker(settings, "inspect", name, check=False).returncode == 0


def image_present(settings, ref):
    return docker(settings, "image", "inspect", ref, check=False).returncode == 0

"""Running external commands and printing progress."""
import os
import subprocess
import sys
import time
from pathlib import Path


def log(msg):
    print(f"{time.strftime('%H:%M:%S')} [core1] {msg}", flush=True)


def warn(msg):
    print(f"{time.strftime('%H:%M:%S')} [core1] WARN: {msg}", file=sys.stderr, flush=True)


class CommandError(RuntimeError):
    pass


def docker_env(settings=None):
    """Process environment with DOCKER_HOST pointing at Docker Desktop's user socket when unset,
    and k3d's helper images pinned."""
    env = dict(os.environ)
    if not env.get("DOCKER_HOST"):
        sock = Path.home() / ".docker" / "run" / "docker.sock"
        if sock.exists():
            env["DOCKER_HOST"] = f"unix://{sock}"
    if settings is not None:
        env["K3D_IMAGE_LOADBALANCER"] = settings.version("K3D_PROXY_IMAGE")
        env["K3D_IMAGE_TOOLS"] = settings.version("K3D_TOOLS_IMAGE")
        env["PATH"] = f"{settings.bin_dir}{os.pathsep}{env.get('PATH', '')}"
    return env


def run(cmd, env=None, check=True, capture=True, timeout=None, input=None):
    """Run cmd (list). Returns CompletedProcess with text output. Raises CommandError on failure if check."""
    try:
        r = subprocess.run([str(c) for c in cmd], env=env, capture_output=capture, text=True,
                           timeout=timeout, input=input)
    except FileNotFoundError as e:
        if check:
            raise CommandError(f"{cmd[0]}: not found") from e
        return subprocess.CompletedProcess(cmd, 127, "", str(e))
    except subprocess.TimeoutExpired as e:
        if check:
            raise CommandError(f"{' '.join(map(str, cmd))}: timed out after {timeout}s") from e
        return subprocess.CompletedProcess(cmd, 124, "", "timeout")
    if check and r.returncode != 0:
        detail = (r.stderr or r.stdout or "").strip() if capture else ""
        raise CommandError(f"{' '.join(map(str, cmd))} failed ({r.returncode}): {detail[-800:]}")
    return r

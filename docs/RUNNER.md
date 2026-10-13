# Unattended runner

`scripts/runner.sh` lets someone (or something) queue `make` targets to run on this machine without
being at the keyboard. It exists because Docker runs here, on the host, and a remote helper may only
have file access to this folder.

Start it in a terminal in the repo root:

```
./scripts/runner.sh
```

What it does, and nothing else:

1. Every 3 seconds it looks for `.runner/inbox/*.cmd`. Each file contains one make target name.
2. If the target is in the allowlist (`doctor bootstrap up down reset status verify verify-quick disk
   endpoints images cluster obs secrets config-repo deploy loadgen agent-kubeconfig wait-green
   scenario-1..5 diag test push`), it runs `make <target>` and writes the output to `.runner/log/<id>.log`
   and the exit code to `.runner/done/<id>.rc`. Anything else is refused.
3. Before most targets it enforces the disk ceiling (`scripts/disk_check.py --enforce`).
4. It touches `.runner/heartbeat` every loop and keeps `.runner/state` current.
5. On macOS it runs under `caffeinate -i`, so the machine does not idle-sleep while it is running.
   Pass `--no-caffeinate` to skip that.

Stop it with Ctrl-C, or `touch .runner/stop`.

Honest limits: the allowlist restricts entry points, not what the Makefile and scripts do. Whoever can
edit this repo can change what a target does. Review the repo before you start the runner if that matters.

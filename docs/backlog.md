# Backlog

Items outside the current phase. Each line says where it came from.

- `core1 diag`: port `scripts/diag.sh` (diagnostics bundle). Not in the `DESIGN.md` CLI list. From the phase 0 inventory.
- Remove the stale `.runner/` line from `.gitignore` when `.gitignore` is extended in phase 1. From phase 0.
- k3d keeps one `k3d-<cluster>-tools` container running per cluster after create. Check whether `core1 up` should
  remove them or leave them. From the phase 0 spike.

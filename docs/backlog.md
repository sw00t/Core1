# Backlog

Items outside the current phase. Each line says where it came from.

- `core1 diag`: port `scripts/diag.sh` (diagnostics bundle). Not in the `DESIGN.md` CLI list. From the phase 0 inventory.
- `core1 up --profile lite`: the fallback profile from `DESIGN.md` section 2. The flag exists and refuses for now.
  From phase 1.
- Pin Python package hashes (`pip install --require-hashes`) for the CLI. Exact versions are pinned today. From phase 1.
- k3d keeps one `k3d-<cluster>-tools` container running per cluster after create. Check whether `core1 up` should
  remove them or leave them. From the phase 0 spike.

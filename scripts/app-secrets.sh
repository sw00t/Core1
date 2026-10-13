#!/usr/bin/env bash
# Platform-owned secrets for the app namespace. These are deliberately NOT in the config repo,
# so the agent's read-only identity cannot see them and the config repo holds no credentials.
. "$(dirname "$0")/lib.sh"
require_cluster
"$KUBECTL" create namespace "$NS_APP" --dry-run=client -o yaml | "$KUBECTL" apply -f - >/dev/null
pw_file="$WORK/orders-db.password"
if [ ! -f "$pw_file" ]; then
  "$PYTHON" -c 'import secrets; print(secrets.token_urlsafe(18))' > "$pw_file"; chmod 600 "$pw_file"
fi
pw=$(cat "$pw_file")
"$KUBECTL" -n "$NS_APP" create secret generic orders-db \
  --from-literal=POSTGRES_USER=orders \
  --from-literal=POSTGRES_PASSWORD="$pw" \
  --from-literal=POSTGRES_DB=orders \
  --from-literal=DB_DSN="postgresql://orders:$pw@postgres.$NS_APP.svc:5432/orders" \
  --dry-run=client -o yaml | "$KUBECTL" apply -f - >/dev/null
log "secret orders-db ensured in $NS_APP"

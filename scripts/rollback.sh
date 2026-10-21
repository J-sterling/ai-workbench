#!/usr/bin/env bash
# Replace the endpoint with the previously deployed image (there is no in-place update).
# Usage: scripts/rollback.sh [--dry-run]
# Warning: recreating the endpoint may change its URL; update Devpost's testing link if so.
set -euo pipefail
cd "$(dirname "$0")/.."
source scripts/nebius-common.sh
[ -f "$HISTORY" ] || die "no deploy history at $HISTORY"
PREV=$(tail -n 2 "$HISTORY" | head -n 1)
[ "$(wc -l < "$HISTORY")" -ge 2 ] || die "only one deploy recorded; nothing to roll back to (use scripts/endpoint.sh stop to take it down)"
PREV_SHA=$(cut -f2 <<<"$PREV")
echo "Previous deploy: commit ${PREV_SHA:0:7}  ($(cut -f1 <<<"$PREV"))"
[ "${1:-}" = "--dry-run" ] && exit 0
ID=$(endpoint_id)
read -r -p "Type 'yes' to delete the current endpoint and recreate it from ${PREV_SHA:0:7}: " answer
[ "$answer" = "yes" ] || die "cancelled"
[ -z "$ID" ] || "$NB" ai endpoint delete --id "$ID"
exec scripts/deploy.sh "$PREV_SHA"

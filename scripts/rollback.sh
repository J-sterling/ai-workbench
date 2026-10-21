#!/usr/bin/env bash
# Put the previously promoted commit back on the live demo (same URL): promote it again, then restart.
# Usage: scripts/rollback.sh [--dry-run]
set -euo pipefail
cd "$(dirname "$0")/.."
source scripts/nebius-common.sh
[ -f "$HISTORY" ] || die "no deploy history at $HISTORY"
PROMOTES=$(awk -F'\t' '$2=="promote"{print $3}' "$HISTORY")
[ "$(wc -l <<<"$PROMOTES")" -ge 2 ] || die "fewer than two promotes recorded; nothing to roll back to"
CURRENT=$(tail -n 1 <<<"$PROMOTES"); PREVIOUS=$(tail -n 2 <<<"$PROMOTES" | head -n 1)
echo "Live: ${CURRENT:0:7}   roll back to: ${PREVIOUS:0:7}"
[ "${1:-}" = "--dry-run" ] && exit 0
read -r -p "Type 'yes' to roll back: " answer
[ "$answer" = "yes" ] || die "cancelled"
exec scripts/promote.sh "$PREVIOUS"

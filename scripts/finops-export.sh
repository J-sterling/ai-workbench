#!/usr/bin/env bash
# Download this contract's Nebius billing (FOCUS 1.2 CSV, from Oct 2026 to this month) and build
# the dashboard's Bills data in var/finops/. Exports are free and read-only.
# Needs NEBIUS_CONTRACT_ID in .env (Console > Billing > Payments > Billing details).
# Usage: scripts/finops-export.sh
set -euo pipefail
cd "$(dirname "$0")/.."
source scripts/nebius-common.sh
CONTRACT=$(sed -n 's/^NEBIUS_CONTRACT_ID=//p' .env 2>/dev/null)
[ -n "$CONTRACT" ] || die "set NEBIUS_CONTRACT_ID in .env"
START=2026-10
END=$(date -u +%Y-%m)

# create waits for the export to finish and prints it; the download link lasts 15 minutes.
ID=$("$NB" billing v1alpha1 one-time-export create --parent-id "$CONTRACT" \
  --start-period "$START" --end-period "$END" --format export_format_focus_1_2_csv \
  --name "ai-workbench-$(date -u +%Y%m%d-%H%M)" | awk '/^  id:/{print $2; exit}')
[ -n "$ID" ] || die "export was not created"
URL=$("$NB" billing v1alpha1 one-time-export get --id "$ID" --format jsonpath='{.status.download_url}')
[ -n "$URL" ] || die "export $ID has no download link yet"

RAW=var/finops/raw
rm -rf "$RAW"; mkdir -p "$RAW"
curl -sSf "$URL" -o "$RAW/export.tar.gz"
tar -xzf "$RAW/export.tar.gz" -C "$RAW"
uv run scripts/finops_build.py

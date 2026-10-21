#!/usr/bin/env bash
# Record that the dashboard now matches the repo (used by scripts/dashboard-sync-check.sh).
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p .claude
{ git rev-parse HEAD; cat docs/tracker/*.json | shasum -a 256 | cut -c1-16; } > .claude/dashboard-synced
echo "Dashboard marked in sync at $(git rev-parse --short HEAD)."

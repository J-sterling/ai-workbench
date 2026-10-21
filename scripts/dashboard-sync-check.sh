#!/usr/bin/env bash
# Claude Code Stop hook: block the end of a turn while the acceptance dashboard is behind the repo.
# "Behind" = commits on HEAD, or edits to docs/tracker/*.json, since scripts/dashboard-synced.sh last ran.
# Reads the hook's JSON on stdin; never blocks twice in a row (stop_hook_active).
set -euo pipefail
cd "$(dirname "$0")/.."
input=$(cat || true)
if printf '%s' "$input" | python3 -c 'import json,sys; sys.exit(0 if json.loads(sys.stdin.read() or "{}").get("stop_hook_active") else 1)' 2>/dev/null; then
  exit 0
fi
marker=.claude/dashboard-synced
head=$(git rev-parse HEAD)
tracker=$(cat docs/tracker/*.json 2>/dev/null | shasum -a 256 | cut -c1-16)
if [ -f "$marker" ]; then
  synced_head=$(sed -n 1p "$marker"); synced_tracker=$(sed -n 2p "$marker")
  [ "$head" = "$synced_head" ] && [ "$tracker" = "$synced_tracker" ] && exit 0
  commits=$(git log --format='%h %s' "$synced_head..HEAD" 2>/dev/null | head -8 || true)
else
  commits="(never synced)"
fi
[ "$tracker" != "${synced_tracker:-}" ] && commits="${commits:+$commits
}docs/tracker/*.json edited since the last sync"
COMMITS="$commits" python3 -c '
import json, os
c = os.environ["COMMITS"].strip()
print(json.dumps({"decision": "block", "reason":
  "Acceptance dashboard is out of date. Changes since the last sync:\n" + c +
  "\nUpdate docs/tracker/*.json, publish both tabs to https://claude.ai/artifact/Fjmp6ChvAShx5zrCK4Tf5D, "
  "then run scripts/dashboard-synced.sh. If nothing on the dashboard needs changing, just run scripts/dashboard-synced.sh."}))'

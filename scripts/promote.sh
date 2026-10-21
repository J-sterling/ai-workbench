#!/usr/bin/env bash
# Ship a tested commit to the live demo without changing its URL:
#   1. the "Promote to demo" workflow retags sha-<commit> as :demo (only CI-published images exist)
#   2. the endpoint restarts and pulls :demo
#   3. /health must report the new commit, then the smoke test runs (if DEMO_PASSWORD is set)
# Usage: scripts/promote.sh [sha] [--no-restart]     (default sha: HEAD)
set -euo pipefail
cd "$(dirname "$0")/.."
source scripts/nebius-common.sh

SHA="${1:-HEAD}"; [ "$SHA" = "--no-restart" ] && { SHA=HEAD; set -- HEAD --no-restart; }
SHA=$(git rev-parse "$SHA")
[ -n "$(image_digest "sha-$SHA")" ] || die "image sha-$SHA isn't published (CI on main must pass first)"

echo "Promoting ${SHA:0:7} to :$DEMO_TAG..."
gh workflow run promote.yml -f sha="$SHA" >/dev/null
sleep 5
RUN_ID=$(gh run list --workflow promote.yml --limit 1 --json databaseId --jq '.[0].databaseId')
gh run watch "$RUN_ID" --exit-status --interval 5 >/dev/null || die "promote workflow failed: gh run view $RUN_ID --log-failed"
DIGEST=$(image_digest "$DEMO_TAG")
record promote "$SHA" "$DIGEST"
echo ":$DEMO_TAG now points at ${SHA:0:7} ($DIGEST)"

[ "${2:-}" = "--no-restart" ] && exit 0
ID=$(endpoint_id)
[ -n "$ID" ] || { echo "No endpoint yet; create it with scripts/deploy.sh"; exit 0; }
"$NB" ai endpoint restart --id "$ID" >/dev/null
echo "Restarted endpoint; waiting for it to serve ${SHA:0:7}..."
URL=$(scripts/endpoint.sh url | python3 -c 'import json,sys
d=sys.stdin.read().strip()
try: v=json.loads(d); print(v[0] if isinstance(v,list) else v)
except Exception: print(d.split()[0] if d else "")')
for _ in $(seq 1 60); do
  V=$(curl -sf "${URL%/}/health" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("version",""))' 2>/dev/null || true)
  [ "$V" = "$SHA" ] && break; sleep 5
done
[ "$V" = "$SHA" ] || die "endpoint still reports '${V:-nothing}' after restart. Restart may not re-pull :$DEMO_TAG; see README (Deploy) for the fallback."
echo "Live: $URL is serving ${SHA:0:7}"
[ -n "${DEMO_PASSWORD:-}" ] && scripts/smoke.sh "$URL" || echo "Set DEMO_PASSWORD to run the smoke test too."

#!/usr/bin/env bash
# Check a deployed demo the way a judge would.
# Usage: DEMO_PASSWORD=... scripts/smoke.sh https://<endpoint-url>
set -euo pipefail
URL="${1:?usage: DEMO_PASSWORD=... $0 <url>}"; URL="${URL%/}"
PW="${DEMO_PASSWORD:?set DEMO_PASSWORD}"
ok() { echo "ok   $*"; }; bad() { echo "FAIL $*"; exit 1; }
[ "$(curl -s -o /dev/null -w '%{http_code}' "$URL/health")" = 200 ] && ok "health" || bad "health"
[ "$(curl -s -o /dev/null -w '%{http_code}' "$URL/samples")" = 401 ] && ok "password required" || bad "password not enforced"
curl -sf --user "judge:$PW" "$URL/config" | grep -q '"models":\["nvidia/nemotron-3-super-120b-a12b"\]' && ok "Super only" || bad "model allowlist"
RID=$(curl -sf --user "judge:$PW" -X POST "$URL/agent/runs" -H 'content-type: application/json' -d '{"sample":"01-garage-down"}' | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])') || bad "start run"
for _ in $(seq 1 90); do
  STATE=$(curl -sf --user "judge:$PW" "$URL/agent/runs/$RID" | python3 -c 'import json,sys; print(json.load(sys.stdin)["status"])')
  [ "$STATE" = running ] || break; sleep 2
done
[ "$STATE" = awaiting_approval ] && ok "Garage run reached the approval step" || bad "run ended as $STATE"

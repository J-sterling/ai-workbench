#!/usr/bin/env bash
# Create the public demo endpoint on Nebius Serverless AI from a CI-published image.
# Usage: scripts/deploy.sh [git-sha]   (default: HEAD, which CI must have published)
# Shows the full config, validates it with --dry-run, and asks before creating anything billable.
set -euo pipefail
cd "$(dirname "$0")/.."
source scripts/nebius-common.sh
require_cpu

SHA="${1:-$(git rev-parse HEAD)}"
DIGEST=$(image_digest "sha-$SHA")
[ -n "$DIGEST" ] || die "image sha-$SHA isn't published yet (wait for CI on main)"
IMAGE="$IMAGE_REPO@$DIGEST"

[ -z "$(endpoint_id)" ] || die "endpoint '$ENDPOINT_NAME' already exists. There is no in-place update: use scripts/rollback.sh to replace it, or scripts/endpoint.sh to stop/start it."

ARGS=(ai endpoint create
  --name "$ENDPOINT_NAME"
  --image "$IMAGE"
  --platform "$PLATFORM" --preset "$PRESET" --disk-size "$DISK_SIZE"
  --container-port 8000
  --env HOST=0.0.0.0 --env KB_BACKEND=memory
  --env-secret "NEBIUS_API_KEY=$SECRET_NAME"
  --env-secret "DEMO_PASSWORD=$SECRET_NAME")
# No --public (the managed https:// URL is enough) and no --auth token (browsers can't send it;
# the app's DEMO_PASSWORD protects it instead).

cat <<INFO
About to create a Nebius Serverless AI endpoint:
  name      $ENDPOINT_NAME
  image     $IMAGE   (commit ${SHA:0:7})
  compute   $PLATFORM / $PRESET, disk $DISK_SIZE
  secrets   NEBIUS_API_KEY, DEMO_PASSWORD from SecretStash '$SECRET_NAME'
  cost      about \$0.066/hour while running (cpu-d3); stop it with scripts/endpoint.sh stop
INFO

echo "Validating with --dry-run..."
"$NB" "${ARGS[@]}" --dry-run >/dev/null

read -r -p "Type 'yes' to create it (billable): " answer
[ "$answer" = "yes" ] || die "cancelled"

"$NB" "${ARGS[@]}"
mkdir -p "$(dirname "$HISTORY")"
printf '%s\t%s\t%s\n' "$(date -u +%FT%TZ)" "$SHA" "$DIGEST" >> "$HISTORY"
echo "Created. Watch it come up with: scripts/endpoint.sh status"

#!/usr/bin/env bash
# Create the public demo endpoint on Nebius Serverless AI (first time only).
# The endpoint runs the moving :demo tag, so later changes ship with scripts/promote.sh
# (retag + restart) and the URL never changes.
# Shows the full config, validates it with --dry-run, and asks before creating anything billable.
set -euo pipefail
cd "$(dirname "$0")/.."
source scripts/nebius-common.sh
require_cpu

DIGEST=$(image_digest "$DEMO_TAG")
[ -n "$DIGEST" ] || die ":$DEMO_TAG doesn't exist yet. Promote a tested commit first: scripts/promote.sh <sha> --no-restart"
[ -z "$(endpoint_id)" ] || die "endpoint '$ENDPOINT_NAME' already exists. Ship changes with scripts/promote.sh; stop/start with scripts/endpoint.sh."
IMAGE="$IMAGE_REPO:$DEMO_TAG"

ARGS=(ai endpoint create
  --name "$ENDPOINT_NAME"
  --image "$IMAGE"
  --platform "$PLATFORM" --preset "$PRESET" --disk-size "$DISK_SIZE"
  --container-port 8000
  --env HOST=0.0.0.0 --env KB_BACKEND=memory
  --env-secret "NEBIUS_API_KEY=$SECRET_NAME"
  --env-secret "DEMO_PASSWORD=$SECRET_NAME"
  --env-secret "TAVILY_API_KEY=$SECRET_NAME")
# No --public (the managed https:// URL is enough) and no --auth token (browsers can't send it;
# the app's DEMO_PASSWORD protects it instead).

cat <<INFO
About to create a Nebius Serverless AI endpoint:
  name      $ENDPOINT_NAME
  image     $IMAGE   (currently $DIGEST)
  compute   $PLATFORM / $PRESET, disk $DISK_SIZE
  secrets   NEBIUS_API_KEY, DEMO_PASSWORD, TAVILY_API_KEY from SecretStash '$SECRET_NAME'
  cost      about \$0.066/hour while running (cpu-d3); stop it with scripts/endpoint.sh stop
INFO

echo "Validating with --dry-run..."
"$NB" "${ARGS[@]}" --dry-run >/dev/null

read -r -p "Type 'yes' to create it (billable): " answer
[ "$answer" = "yes" ] || die "cancelled"

"$NB" "${ARGS[@]}"
record create "-" "$DIGEST"
echo "Created. Watch it come up with: scripts/endpoint.sh status"

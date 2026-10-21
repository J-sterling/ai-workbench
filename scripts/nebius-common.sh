# Shared settings for the Nebius deploy scripts. Source it; don't run it.
NB="${NEBIUS_BIN:-$HOME/.nebius/bin/nebius}"
ENDPOINT_NAME="${ENDPOINT_NAME:-ai-workbench}"
SECRET_NAME="${SECRET_NAME:-ai-workbench-secrets}"
# Smallest CPU preset. The CLI's defaults are an H100 GPU and a 250 GiB disk, so always pass these.
PLATFORM="${PLATFORM:-cpu-d3}"
PRESET="${PRESET:-2vcpu-8gb}"
DISK_SIZE="${DISK_SIZE:-20Gi}"
IMAGE_REPO="ghcr.io/j-sterling/ai-workbench"
# The endpoint always runs this moving tag; scripts/promote.sh points it at a tested sha- image.
DEMO_TAG="demo"
HISTORY="$(git rev-parse --show-toplevel)/deploy/history.log"

die() { echo "error: $*" >&2; exit 1; }

require_cpu() {
  case "$PLATFORM" in cpu-*) ;; *) die "PLATFORM must be a CPU platform (got $PLATFORM)";; esac
  case "$DISK_SIZE" in [0-9]Gi|[1-4][0-9]Gi) ;; *) die "DISK_SIZE must be under 50Gi (got $DISK_SIZE)";; esac
}

# Digest of a published sha- tag, so the endpoint can't silently change image.
image_digest() {
  local tag="$1" token
  token=$(curl -sf "https://ghcr.io/token?scope=repository:j-sterling/ai-workbench:pull" | python3 -c 'import json,sys; print(json.load(sys.stdin)["token"])') || die "can't reach ghcr.io"
  curl -sfI -H "Authorization: Bearer $token" \
    -H 'Accept: application/vnd.oci.image.index.v1+json, application/vnd.docker.distribution.manifest.v2+json' \
    "https://ghcr.io/v2/j-sterling/ai-workbench/manifests/$tag" | tr -d '\r' | awk -F': ' 'tolower($1)=="docker-content-digest"{print $2}'
}

endpoint_id() { "$NB" ai endpoint get-by-name --name "$ENDPOINT_NAME" --format jsonpath='{.metadata.id}' 2>/dev/null || true; }

# history.log columns: time  action  commit  digest
record() { mkdir -p "$(dirname "$HISTORY")"; printf '%s\t%s\t%s\t%s\n' "$(date -u +%FT%TZ)" "$1" "$2" "$3" >> "$HISTORY"; }

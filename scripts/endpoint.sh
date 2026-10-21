#!/usr/bin/env bash
# Stop, start or inspect the demo endpoint. A stopped endpoint isn't billed for compute or storage.
# Usage: scripts/endpoint.sh status|stop|start|restart|url|logs
set -euo pipefail
cd "$(dirname "$0")/.."
source scripts/nebius-common.sh
ID=$(endpoint_id); [ -n "$ID" ] || die "no endpoint named '$ENDPOINT_NAME'"
case "${1:-status}" in
  status) "$NB" ai endpoint get --id "$ID" --format jsonpath='{.status.state}{"\n"}{.status.public_endpoints}{"\n"}' ;;
  url)    "$NB" ai endpoint get --id "$ID" --format jsonpath='{.status.public_endpoints}' ;;
  stop)   "$NB" ai endpoint stop --id "$ID" && echo "Stopped (no compute billing). Must be running from submission until 15 Dec." ;;
  start)  "$NB" ai endpoint start --id "$ID" ;;
  restart) "$NB" ai endpoint restart --id "$ID" ;;
  logs)   "$NB" ai endpoint logs --id "$ID" ;;
  *) die "usage: $0 status|stop|start|restart|url|logs" ;;
esac

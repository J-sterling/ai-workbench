#!/usr/bin/env bash
# Copy one API key out of the Ansible vault into .env without printing it.
# Only that variable's line in .env changes; everything else is kept.
# Prompts for the vault password.
# Usage: scripts/key-from-vault.sh [name-in-vault] [ENV_VAR] [path/to/vault.yml]
#   scripts/key-from-vault.sh                          # nebius -> NEBIUS_API_KEY
#   scripts/key-from-vault.sh tavily TAVILY_API_KEY
set -euo pipefail

NAME="$(printf '%s' "${1:-nebius}" | tr '[:upper:]' '[:lower:]')"
VAR="${2:-NEBIUS_API_KEY}"
VAULT="${3:-$HOME/Documents/ansible/group_vars/all/vault.yml}"
cd "$(dirname "$0")/.."

value=$(ansible-vault view "$VAULT" |
  awk -v name="$NAME" 'tolower($0) ~ ("^[a-z0-9_]*" name "[a-z0-9_]*:") {sub(/^[^:]*:[ \t]*/,""); gsub(/["\047]/,""); print; exit}')

if [ -z "$value" ]; then
  echo "No variable with '$NAME' in its name found in $VAULT" >&2
  exit 1
fi

umask 077
[ -f .env ] || cp .env.example .env
tmp=$(mktemp .env.XXXXXX)
{ grep -v "^${VAR}=" .env || true; printf '%s=%s\n' "$VAR" "$value"; } > "$tmp"
mv "$tmp" .env
echo "Wrote $VAR to .env (${#value} chars, not shown); other lines kept"

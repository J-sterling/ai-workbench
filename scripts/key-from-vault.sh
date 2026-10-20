#!/usr/bin/env bash
# Copy the Nebius API key out of the Ansible vault into .env without printing it.
# Prompts for the vault password. Usage: scripts/key-from-vault.sh [path/to/vault.yml]
set -euo pipefail

VAULT="${1:-$HOME/Documents/ansible/group_vars/all/vault.yml}"
cd "$(dirname "$0")/.."

line=$(ansible-vault view "$VAULT" |
  awk 'tolower($0) ~ /^[a-z_]*nebius[a-z_]*:/ {sub(/^[^:]*:[ \t]*/,""); gsub(/["\047]/,""); print "NEBIUS_API_KEY=" $0; exit}')

if [ -z "$line" ] || [ "$line" = "NEBIUS_API_KEY=" ]; then
  echo "No variable with 'nebius' in its name found in $VAULT" >&2
  exit 1
fi

umask 077
{ grep -v '^NEBIUS_API_KEY=' .env.example; echo "$line"; } > .env
echo "Wrote NEBIUS_API_KEY to .env (${#line} chars, not shown)"

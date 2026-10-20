#!/usr/bin/env bash
# Use the repo's hooks in .githooks (secret scan + offline tests before each commit).
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
git config core.hooksPath .githooks
echo "Hooks installed: commits now run gitleaks and the offline tests."

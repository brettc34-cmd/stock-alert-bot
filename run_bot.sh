#!/usr/bin/env bash

set -euo pipefail

cd "$(dirname "$0")" || exit 1

if [[ -f .env ]]; then
	set -a
	source .env
	set +a
fi

# Use PYTHON env var or fallback to python3
PYTHON=${PYTHON:-python3}

$PYTHON bot.py >> bot.log 2>&1
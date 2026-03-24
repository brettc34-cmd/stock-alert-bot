#!/usr/bin/env bash

set -euo pipefail

cd "$(dirname "$0")" || exit 1

if [[ -f .env ]]; then
  set -a
  source .env
  set +a
fi

PYTHON=${PYTHON:-python3}

if [[ ! -d .venv ]]; then
  echo "error: .venv not found. Create it with: python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt" >&2
  exit 1
fi

source .venv/bin/activate
exec "$PYTHON" interactive_discord_bot.py

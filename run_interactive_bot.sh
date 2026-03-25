#!/usr/bin/env bash

set -euo pipefail

cd "$(dirname "$0")" || exit 1

if [[ -f .env ]]; then
  set -a
  source .env
  set +a
fi

if [[ ! -d .venv ]]; then
  echo "error: .venv not found. Create it with: python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt" >&2
  exit 1
fi

PYTHON=${PYTHON:-"$(pwd)/.venv/bin/python3.13"}
if [[ ! -x "$PYTHON" ]]; then
  PYTHON="$(pwd)/.venv/bin/python3"
fi
if [[ ! -x "$PYTHON" ]]; then
  PYTHON="$(pwd)/.venv/bin/python"
fi

exec "$PYTHON" interactive_discord_bot.py

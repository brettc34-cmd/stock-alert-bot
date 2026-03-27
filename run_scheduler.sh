#!/usr/bin/env bash
# Start the bot in scheduler mode using the local venv Python.
set -euo pipefail
cd "$(dirname "$0")"

if [[ -f .env ]]; then
    set -a
    source .env
    set +a
fi

PYTHON="$(dirname "$0")/.venv/bin/python3.13"
if [[ ! -x "$PYTHON" ]]; then
    PYTHON="$(dirname "$0")/.venv/bin/python3"
fi
if [[ ! -x "$PYTHON" ]]; then
    PYTHON="$(dirname "$0")/.venv/bin/python"
fi

if [[ "${WEBHOOK_STARTUP_SELF_CHECK:-1}" =~ ^(1|true|yes|on)$ ]]; then
    "$PYTHON" bot.py --self-check-webhook
fi

exec "$PYTHON" bot.py --scheduler

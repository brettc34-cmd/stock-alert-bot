#!/usr/bin/env bash

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SERVICE_NAME="stock-alert-bot.service"
SYSTEMD_SRC="$PROJECT_ROOT/systemd/$SERVICE_NAME"
SYSTEMD_DIR="${SYSTEMD_DIR:-/etc/systemd/system}"
ETC_DIR="${ETC_DIR:-/etc}"
ENV_PATH="$ETC_DIR/stock-alert-bot.env"
RUN_USER="${RUN_USER:-$(id -un)}"
TMP_SERVICE="$(mktemp)"

trap 'rm -f "$TMP_SERVICE"' EXIT

sed \
  -e "s|__PROJECT_ROOT__|$PROJECT_ROOT|g" \
  -e "s|__SERVICE_USER__|$RUN_USER|g" \
  "$SYSTEMD_SRC" > "$TMP_SERVICE"

install -d "$SYSTEMD_DIR"
install -m 0644 "$TMP_SERVICE" "$SYSTEMD_DIR/$SERVICE_NAME"

if [[ ! -f "$ENV_PATH" ]]; then
  install -d "$ETC_DIR"
  cp "$PROJECT_ROOT/.env.example" "$ENV_PATH"
  chmod 0600 "$ENV_PATH"
fi

if [[ "${SKIP_SYSTEMCTL:-0}" == "1" ]]; then
  echo "Installed service file to $SYSTEMD_DIR/$SERVICE_NAME"
  echo "Created env file at $ENV_PATH"
  exit 0
fi

systemctl daemon-reload
systemctl enable "$SERVICE_NAME"
systemctl restart "$SERVICE_NAME"
systemctl status "$SERVICE_NAME" --no-pager

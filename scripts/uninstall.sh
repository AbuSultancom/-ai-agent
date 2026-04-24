#!/usr/bin/env bash
# uninstall.sh — removes the AI Agent systemd service and CLI wrapper
# Usage: sudo bash scripts/uninstall.sh

set -euo pipefail

SERVICE_NAME="ai-agent"
SYSTEMD_DIR="/etc/systemd/system"
CLI_BIN="/usr/local/bin/ai"

if [[ $EUID -ne 0 ]]; then
  echo "❌  Run as root:  sudo bash scripts/uninstall.sh" >&2
  exit 1
fi

echo "🛑  Stopping and disabling $SERVICE_NAME…"
systemctl stop "$SERVICE_NAME" 2>/dev/null || true
systemctl disable "$SERVICE_NAME" 2>/dev/null || true

if [[ -f "$SYSTEMD_DIR/$SERVICE_NAME.service" ]]; then
  rm "$SYSTEMD_DIR/$SERVICE_NAME.service"
  echo "🗑️   Removed $SYSTEMD_DIR/$SERVICE_NAME.service"
fi

systemctl daemon-reload

if [[ -f "$CLI_BIN" ]]; then
  rm "$CLI_BIN"
  echo "🗑️   Removed $CLI_BIN"
fi

echo "✅  AI Agent service uninstalled. Data and config files are untouched."

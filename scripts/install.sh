#!/usr/bin/env bash
# install.sh — installs AI Agent as a persistent systemd service
# Usage: sudo bash scripts/install.sh

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVICE_NAME="ai-agent"
SERVICE_FILE="$REPO_DIR/ai-agent.service"
SYSTEMD_DIR="/etc/systemd/system"
CLI_BIN="/usr/local/bin/ai"

# ── Checks ──────────────────────────────────────────────────────────────────
if [[ $EUID -ne 0 ]]; then
  echo "❌  Run as root:  sudo bash scripts/install.sh" >&2
  exit 1
fi

if ! command -v python3 &>/dev/null; then
  echo "❌  python3 not found" >&2; exit 1
fi

if ! command -v systemctl &>/dev/null; then
  echo "❌  systemd not available on this system" >&2; exit 1
fi

# ── .env check ──────────────────────────────────────────────────────────────
if [[ ! -f "$REPO_DIR/.env" ]]; then
  echo "⚠️   No .env found — copying .env.example"
  cp "$REPO_DIR/.env.example" "$REPO_DIR/.env"
  echo "    Edit $REPO_DIR/.env and set ANTHROPIC_API_KEY, then re-run this script."
  exit 0
fi

# ── Install Python deps ──────────────────────────────────────────────────────
echo "📦  Installing Python dependencies…"
python3 -m pip install -q -r "$REPO_DIR/requirements.txt"

# ── Patch service file with actual repo path ─────────────────────────────────
TMP_SERVICE=$(mktemp)
sed "s|/home/user/-ai-agent|$REPO_DIR|g" "$SERVICE_FILE" > "$TMP_SERVICE"

# Set User= to current calling user (whoever ran sudo)
REAL_USER="${SUDO_USER:-root}"
sed -i "s|^User=.*|User=$REAL_USER|" "$TMP_SERVICE"

# ── Install service ──────────────────────────────────────────────────────────
echo "🔧  Installing systemd unit…"
cp "$TMP_SERVICE" "$SYSTEMD_DIR/$SERVICE_NAME.service"
rm "$TMP_SERVICE"
chmod 644 "$SYSTEMD_DIR/$SERVICE_NAME.service"

systemctl daemon-reload
systemctl enable "$SERVICE_NAME"
systemctl restart "$SERVICE_NAME"

# ── Install CLI wrapper ──────────────────────────────────────────────────────
echo "🔗  Installing CLI → $CLI_BIN"
cp "$REPO_DIR/scripts/ai" "$CLI_BIN"
chmod +x "$CLI_BIN"

# ── Done ────────────────────────────────────────────────────────────────────
sleep 1
STATUS=$(systemctl is-active "$SERVICE_NAME" 2>/dev/null || echo "unknown")
if [[ "$STATUS" == "active" ]]; then
  echo ""
  echo "✅  AI Agent service is running!"
  echo "    Dashboard : http://localhost:5000"
  echo "    CLI       : ai \"your task here\""
  echo "    Logs      : ai logs  (or: journalctl -u ai-agent -f)"
  echo "    Stop      : sudo systemctl stop ai-agent"
else
  echo ""
  echo "⚠️   Service status: $STATUS"
  echo "    Check logs: journalctl -u $SERVICE_NAME -n 40"
fi

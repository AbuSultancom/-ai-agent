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
  echo "⚠️   No .env found — launching configuration wizard…"
  cp "$REPO_DIR/.env.example" "$REPO_DIR/.env"
  python3 "$REPO_DIR/scripts/ai-config" --first-run
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

# ── Install CLI wrappers ─────────────────────────────────────────────────────
echo "🔗  Installing CLI tools…"
cp "$REPO_DIR/scripts/ai" "$CLI_BIN"
chmod +x "$CLI_BIN"

cp "$REPO_DIR/scripts/aish" "/usr/local/bin/aish"
chmod +x "/usr/local/bin/aish"

cp "$REPO_DIR/scripts/ai-config" "/usr/local/bin/ai-config"
chmod +x "/usr/local/bin/ai-config"

echo "    → /usr/local/bin/ai        (CLI task runner)"
echo "    → /usr/local/bin/aish      (AI Shell)"
echo "    → /usr/local/bin/ai-config (configuration manager)"

# ── Done ────────────────────────────────────────────────────────────────────
sleep 1
STATUS=$(systemctl is-active "$SERVICE_NAME" 2>/dev/null || echo "unknown")
PORT=$(grep -E '^PORT=' "$REPO_DIR/.env" 2>/dev/null | cut -d= -f2 | tr -d ' ' || echo "5000")
PORT="${PORT:-5000}"

if [[ "$STATUS" == "active" ]]; then
  echo ""
  echo "✅  AI Agent service is running!"
  echo "    Dashboard  : http://localhost:${PORT}"
  echo "    CLI        : ai \"your task here\""
  echo "    AI Shell   : aish"
  echo "    Configure  : ai-config"
  echo "    Logs       : ai logs  (or: journalctl -u ai-agent -f)"
  echo "    Stop       : sudo systemctl stop ai-agent"
else
  echo ""
  echo "⚠️   Service status: $STATUS"
  echo "    Check logs: journalctl -u $SERVICE_NAME -n 40"
fi

#!/usr/bin/env bash
# setup.sh — One-liner remote installer for AI Agent
#
# Usage (run directly from GitHub):
#   curl -fsSL https://raw.githubusercontent.com/abusultancom/-ai-agent/main/scripts/setup.sh | bash
#
# Or with a custom install directory:
#   curl -fsSL .../setup.sh | INSTALL_DIR=/opt/ai-agent bash

set -euo pipefail

# ── Config ────────────────────────────────────────────────────────────────────
REPO_URL="https://github.com/abusultancom/-ai-agent.git"
INSTALL_DIR="${INSTALL_DIR:-$HOME/.ai-agent}"
BRANCH="${BRANCH:-main}"
MIN_PYTHON="3.10"

# ── Colors ────────────────────────────────────────────────────────────────────
R="\033[91m"; G="\033[92m"; Y="\033[93m"; B="\033[94m"
C="\033[96m"; W="\033[97m"; D="\033[2m"; BOLD="\033[1m"; RESET="\033[0m"

banner() {
  echo -e "${C}${BOLD}"
  echo '  █████╗ ██╗    █████╗  ██████╗ ███████╗███╗   ██╗████████╗'
  echo ' ██╔══██╗██║   ██╔══██╗██╔════╝ ██╔════╝████╗  ██║╚══██╔══╝'
  echo ' ███████║██║   ███████║██║  ███╗█████╗  ██╔██╗ ██║   ██║   '
  echo ' ██╔══██║██║   ██╔══██║██║   ██║██╔══╝  ██║╚██╗██║   ██║   '
  echo ' ██║  ██║██║   ██║  ██║╚██████╔╝███████╗██║ ╚████║   ██║   '
  echo ' ╚═╝  ╚═╝╚═╝   ╚═╝  ╚═╝ ╚═════╝ ╚══════╝╚═╝  ╚═══╝   ╚═╝   '
  echo -e "${RESET}${D}  AI Agent — Installer${RESET}"
  echo ""
}

info()    { echo -e "${B}[•]${RESET} $*"; }
ok()      { echo -e "${G}[✓]${RESET} $*"; }
warn()    { echo -e "${Y}[!]${RESET} $*"; }
fail()    { echo -e "${R}[✗]${RESET} $*" >&2; exit 1; }
step()    { echo -e "\n${BOLD}${W}── $* ──${RESET}"; }

# ── Prerequisite checks ───────────────────────────────────────────────────────
check_prereqs() {
  step "Checking prerequisites"

  # python3
  if ! command -v python3 &>/dev/null; then
    warn "python3 not found — attempting to install…"
    if command -v apt-get &>/dev/null; then
      sudo apt-get update -qq && sudo apt-get install -y -qq python3 python3-pip python3-venv
    elif command -v dnf &>/dev/null; then
      sudo dnf install -y python3 python3-pip
    elif command -v brew &>/dev/null; then
      brew install python3
    else
      fail "Cannot install python3 automatically. Please install Python 3.10+ and re-run."
    fi
  fi

  # version check
  PY_VER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
  PY_OK=$(python3 -c "import sys; print(int(sys.version_info >= (3,10)))")
  if [[ "$PY_OK" != "1" ]]; then
    fail "Python $MIN_PYTHON+ required (found $PY_VER). Please upgrade Python."
  fi
  ok "Python $PY_VER"

  # git
  if ! command -v git &>/dev/null; then
    warn "git not found — attempting to install…"
    if command -v apt-get &>/dev/null; then
      sudo apt-get install -y -qq git
    elif command -v dnf &>/dev/null; then
      sudo dnf install -y git
    elif command -v brew &>/dev/null; then
      brew install git
    else
      fail "Cannot install git automatically. Please install git and re-run."
    fi
  fi
  ok "git $(git --version | awk '{print $3}')"

  # pip
  if ! python3 -m pip --version &>/dev/null; then
    warn "pip not found — attempting to install…"
    python3 -m ensurepip --upgrade 2>/dev/null || \
      curl -fsSL https://bootstrap.pypa.io/get-pip.py | python3
  fi
  ok "pip $(python3 -m pip --version | awk '{print $2}')"

  # curl (needed if script was piped, but let's verify)
  command -v curl &>/dev/null && ok "curl available" || warn "curl not found (continuing anyway)"
}

# ── Clone or update repo ──────────────────────────────────────────────────────
clone_or_update() {
  step "Fetching repository"

  if [[ -d "$INSTALL_DIR/.git" ]]; then
    info "Repository already exists at $INSTALL_DIR — updating…"
    git -C "$INSTALL_DIR" fetch origin "$BRANCH" --quiet
    git -C "$INSTALL_DIR" checkout "$BRANCH" --quiet
    git -C "$INSTALL_DIR" pull origin "$BRANCH" --quiet
    ok "Repository updated"
  else
    info "Cloning $REPO_URL → $INSTALL_DIR"
    git clone --branch "$BRANCH" --depth 1 "$REPO_URL" "$INSTALL_DIR" --quiet
    ok "Repository cloned"
  fi
}

# ── Install Python dependencies ───────────────────────────────────────────────
install_deps() {
  step "Installing Python dependencies"
  cd "$INSTALL_DIR"

  # Optional: use a venv if not already in one
  if [[ -z "${VIRTUAL_ENV:-}" ]] && [[ "${USE_VENV:-1}" == "1" ]]; then
    if [[ ! -d "$INSTALL_DIR/.venv" ]]; then
      info "Creating virtual environment…"
      python3 -m venv "$INSTALL_DIR/.venv"
    fi
    # shellcheck source=/dev/null
    source "$INSTALL_DIR/.venv/bin/activate"
    ok "Virtual environment active"
  fi

  info "Running pip install…"
  python3 -m pip install -q -r requirements.txt
  ok "Dependencies installed"
}

# ── Configure .env ────────────────────────────────────────────────────────────
configure_env() {
  step "Configuration"
  cd "$INSTALL_DIR"

  if [[ ! -f ".env" ]]; then
    cp .env.example .env
    info "Created .env from template"
  else
    info ".env already exists — skipping creation"
  fi

  # Always run the interactive config wizard
  info "Launching configuration wizard…"
  echo ""
  python3 scripts/ai-config --first-run
}

# ── Install system service and CLI tools ──────────────────────────────────────
install_service() {
  step "System integration"
  cd "$INSTALL_DIR"

  if command -v systemctl &>/dev/null; then
    if [[ $EUID -ne 0 ]]; then
      info "Installing systemd service (requires sudo)…"
      sudo bash scripts/install.sh
    else
      bash scripts/install.sh
    fi
  else
    warn "systemd not available — skipping service installation"
    warn "To start manually: cd $INSTALL_DIR && python3 orchestrator.py serve"

    # Install CLI tools manually (no systemd path)
    if [[ $EUID -eq 0 ]]; then
      cp "$INSTALL_DIR/scripts/ai" /usr/local/bin/ai
      chmod +x /usr/local/bin/ai
      cp "$INSTALL_DIR/scripts/aish" /usr/local/bin/aish
      chmod +x /usr/local/bin/aish
      cp "$INSTALL_DIR/scripts/ai-config" /usr/local/bin/ai-config
      chmod +x /usr/local/bin/ai-config
      ok "CLI tools installed → /usr/local/bin/{ai,aish,ai-config}"
    else
      info "Skipping global CLI install (not root)"
      info "Add $INSTALL_DIR/scripts to your PATH to use ai/aish/ai-config"
    fi
  fi
}

# ── Done ──────────────────────────────────────────────────────────────────────
print_summary() {
  PORT=$(grep -E '^PORT=' "$INSTALL_DIR/.env" 2>/dev/null | cut -d= -f2 | tr -d ' ' || echo "5000")
  PORT="${PORT:-5000}"

  echo ""
  echo -e "${G}${BOLD}╔══════════════════════════════════════════════╗${RESET}"
  echo -e "${G}${BOLD}║        AI Agent installed successfully!      ║${RESET}"
  echo -e "${G}${BOLD}╚══════════════════════════════════════════════╝${RESET}"
  echo ""
  echo -e "  ${BOLD}Dashboard${RESET}  →  http://localhost:${PORT}"
  echo -e "  ${BOLD}CLI${RESET}        →  ai \"your task here\""
  echo -e "  ${BOLD}AI Shell${RESET}   →  aish"
  echo -e "  ${BOLD}Configure${RESET}  →  ai-config"
  echo -e "  ${BOLD}Logs${RESET}       →  ai logs"
  echo -e "  ${BOLD}Restart${RESET}    →  sudo systemctl restart ai-agent"
  echo ""
  echo -e "  ${D}Install dir: $INSTALL_DIR${RESET}"
  echo ""
}

# ── Entry point ───────────────────────────────────────────────────────────────
main() {
  clear 2>/dev/null || true
  banner

  check_prereqs
  clone_or_update
  install_deps
  configure_env
  install_service
  print_summary
}

main "$@"

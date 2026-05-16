#!/usr/bin/env bash
# AI Agent — one-shot setup script (Linux / macOS)
set -e

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  AI Agent — Setup"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# 1. Python check
if ! command -v python3 &>/dev/null; then
  echo "❌ Python 3 not found. Install it from https://python.org" && exit 1
fi
echo "✅ Python: $(python3 --version)"

# 2. Install Python dependencies
echo ""
echo "📦 Installing Python packages..."
pip install -r requirements.txt

# 3. Install Playwright browser (Chromium)
echo ""
echo "🌐 Installing Playwright Chromium browser..."
playwright install chromium

# 4. Copy .env if not present
if [ ! -f .env ]; then
  cp .env.example .env
  echo ""
  echo "📝 Created .env from .env.example"
  echo "   → Open .env and set your ANTHROPIC_API_KEY"
else
  echo "✅ .env already exists"
fi

# 5. Create data directories
mkdir -p data/chromadb data/screenshots data/uploads

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  ✅ Setup complete!"
echo ""
echo "  Next steps:"
echo "   1. Edit .env and set ANTHROPIC_API_KEY"
echo "   2. Run: python orchestrator.py serve"
echo "   3. Open: http://localhost:5000"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

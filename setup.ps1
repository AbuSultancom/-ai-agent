# AI Agent — one-shot setup script (Windows PowerShell)
$ErrorActionPreference = "Stop"

Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan
Write-Host "  AI Agent — Setup" -ForegroundColor Cyan
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan

# 1. Python check
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Host "❌ Python not found. Install from https://python.org" -ForegroundColor Red
    exit 1
}
Write-Host "✅ Python: $(python --version)"

# 2. Install Python dependencies
Write-Host ""
Write-Host "📦 Installing Python packages..." -ForegroundColor Yellow
pip install -r requirements.txt

# 3. Install Playwright browser (Chromium)
Write-Host ""
Write-Host "🌐 Installing Playwright Chromium browser..." -ForegroundColor Yellow
playwright install chromium

# 4. Copy .env if not present
if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host ""
    Write-Host "📝 Created .env from .env.example" -ForegroundColor Green
    Write-Host "   → Open .env and set your ANTHROPIC_API_KEY" -ForegroundColor Yellow
} else {
    Write-Host "✅ .env already exists"
}

# 5. Create data directories
New-Item -ItemType Directory -Force -Path "data\chromadb", "data\screenshots", "data\uploads" | Out-Null

Write-Host ""
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan
Write-Host "  ✅ Setup complete!" -ForegroundColor Green
Write-Host ""
Write-Host "  Next steps:"
Write-Host "   1. Edit .env and set ANTHROPIC_API_KEY"
Write-Host "   2. Run: python orchestrator.py serve"
Write-Host "   3. Open: http://localhost:5000"
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan

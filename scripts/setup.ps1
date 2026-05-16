# setup.ps1 — One-liner installer for AI Agent on Windows
#
# Usage (run in PowerShell as Administrator):
#   iex (irm "https://raw.githubusercontent.com/abusultancom/-ai-agent/main/scripts/setup.ps1")
#
# Or with custom install directory:
#   $env:INSTALL_DIR = "C:\ai-agent"; iex (irm "...")

$ErrorActionPreference = "Stop"

$REPO_URL   = "https://github.com/abusultancom/-ai-agent.git"
$INSTALL_DIR = if ($env:INSTALL_DIR) { $env:INSTALL_DIR } else { "$HOME\.ai-agent" }
$BRANCH     = if ($env:BRANCH) { $env:BRANCH } else { "main" }
$MIN_PYTHON = [version]"3.10"

# ── Colors ────────────────────────────────────────────────────────────────────
function info  { Write-Host "[•] $args" -ForegroundColor Cyan }
function ok    { Write-Host "[✓] $args" -ForegroundColor Green }
function warn  { Write-Host "[!] $args" -ForegroundColor Yellow }
function fail  { Write-Host "[✗] $args" -ForegroundColor Red; exit 1 }
function step  { Write-Host "`n── $args ──" -ForegroundColor White }

Write-Host @"

  █████╗ ██╗    █████╗  ██████╗ ███████╗███╗   ██╗████████╗
 ██╔══██╗██║   ██╔══██╗██╔════╝ ██╔════╝████╗  ██║╚══██╔══╝
 ███████║██║   ███████║██║  ███╗█████╗  ██╔██╗ ██║   ██║
 ██╔══██║██║   ██╔══██║██║   ██║██╔══╝  ██║╚██╗██║   ██║
 ██║  ██║██║   ██║  ██║╚██████╔╝███████╗██║ ╚████║   ██║
 ╚═╝  ╚═╝╚═╝   ╚═╝  ╚═╝ ╚═════╝ ╚══════╝╚═╝  ╚═══╝   ╚═╝

  AI Agent — Windows Installer
"@ -ForegroundColor Cyan

# ── Check Python ──────────────────────────────────────────────────────────────
step "Checking prerequisites"

$python = $null
foreach ($cmd in @("python", "python3", "py")) {
    try {
        $ver = & $cmd --version 2>&1
        if ($ver -match "Python (\d+\.\d+)") {
            $pyVer = [version]$Matches[1]
            if ($pyVer -ge $MIN_PYTHON) { $python = $cmd; break }
        }
    } catch {}
}

if (-not $python) {
    warn "Python $MIN_PYTHON+ not found."
    info "Opening Python download page..."
    Start-Process "https://www.python.org/downloads/"
    fail "Install Python 3.10+ then re-run this script."
}
ok "Python found: $python ($($pyVer))"

# ── Check Git ─────────────────────────────────────────────────────────────────
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    warn "Git not found."
    info "Opening Git download page..."
    Start-Process "https://git-scm.com/download/win"
    fail "Install Git then re-run this script."
}
ok "Git found"

# ── Clone repo ────────────────────────────────────────────────────────────────
step "Cloning repository"

if (Test-Path $INSTALL_DIR) {
    info "Directory exists — pulling latest changes..."
    Push-Location $INSTALL_DIR
    git pull origin $BRANCH
    Pop-Location
} else {
    git clone --branch $BRANCH $REPO_URL $INSTALL_DIR
}
ok "Repository ready at $INSTALL_DIR"

# ── Virtual environment ───────────────────────────────────────────────────────
step "Setting up Python environment"

$venvDir = "$INSTALL_DIR\.venv"
if (-not (Test-Path $venvDir)) {
    & $python -m venv $venvDir
    ok "Virtual environment created"
}

$pip = "$venvDir\Scripts\pip.exe"
$pythonExe = "$venvDir\Scripts\python.exe"

& $pip install -q --upgrade pip
& $pip install -q -r "$INSTALL_DIR\requirements.txt"
ok "Dependencies installed"

# ── Configure .env ────────────────────────────────────────────────────────────
step "Configuration"

$envFile = "$INSTALL_DIR\.env"
if (-not (Test-Path $envFile)) {
    Copy-Item "$INSTALL_DIR\.env.example" $envFile
    ok "Created .env from template"

    $apiKey = Read-Host "`nEnter your Anthropic API key (leave blank to use Ollama only)"
    if ($apiKey) {
        (Get-Content $envFile) -replace "ANTHROPIC_API_KEY=.*", "ANTHROPIC_API_KEY=$apiKey" |
            Set-Content $envFile
        ok "API key saved"
    } else {
        $localModel = Read-Host "Enter local Ollama model name (default: llama3.2)"
        if (-not $localModel) { $localModel = "llama3.2" }
        (Get-Content $envFile) -replace "LOCAL_MODEL=.*", "LOCAL_MODEL=$localModel" |
            Set-Content $envFile
        ok "Local model set to: $localModel"
    }
} else {
    ok ".env already exists — skipping configuration"
}

# ── Create start.bat ──────────────────────────────────────────────────────────
$startBat = "$INSTALL_DIR\start.bat"
@"
@echo off
cd /d "%~dp0"
call .venv\Scripts\activate.bat
python orchestrator.py serve
"@ | Set-Content $startBat
ok "Created start.bat"

# ── Desktop shortcut ──────────────────────────────────────────────────────────
$desktop = [Environment]::GetFolderPath("Desktop")
$shortcut = "$desktop\AI Agent.lnk"
$wsh = New-Object -ComObject WScript.Shell
$sc = $wsh.CreateShortcut($shortcut)
$sc.TargetPath = $startBat
$sc.WorkingDirectory = $INSTALL_DIR
$sc.IconLocation = "cmd.exe"
$sc.Description = "AI Agent Server"
$sc.Save()
ok "Desktop shortcut created"

# ── Done ──────────────────────────────────────────────────────────────────────
Write-Host @"

╔══════════════════════════════════════════════╗
║          AI Agent installed!                 ║
║                                              ║
║  Start:   double-click 'AI Agent' on desktop ║
║     or:   run start.bat in $INSTALL_DIR
║                                              ║
║  Dashboard: http://localhost:5000            ║
╚══════════════════════════════════════════════╝
"@ -ForegroundColor Green

# ai.ps1 — Windows CLI for AI Agent (equivalent of the Linux `ai` command)
#
# Setup (run once as Administrator):
#   Copy-Item scripts\ai.ps1 "$env:ProgramFiles\ai-agent\ai.ps1"
#   Add to PATH or create alias in $PROFILE:
#     function ai { & "C:\Program Files\ai-agent\ai.ps1" @args }
#
# Usage:
#   ai "Write a Python script that counts words"
#   ai chat "Explain quantum computing"
#   ai status
#   ai logs

param(
    [Parameter(Position=0)] [string]$Command = "",
    [Parameter(Position=1, ValueFromRemainingArguments)] [string[]]$Args
)

$BASE_URL = if ($env:AI_AGENT_URL) { $env:AI_AGENT_URL } else { "http://localhost:5000" }

function Invoke-Task($task) {
    $body = @{ task = $task } | ConvertTo-Json
    try {
        $r = Invoke-RestMethod -Uri "$BASE_URL/api/task/run" -Method POST `
             -Body $body -ContentType "application/json" -TimeoutSec 120
        Write-Host ($r.output ?? $r.error ?? ($r | ConvertTo-Json))
    } catch {
        Write-Host "[error] $($_.Exception.Message)" -ForegroundColor Red
    }
}

function Invoke-Chat($message) {
    $body = @{ message = $message } | ConvertTo-Json
    try {
        $r = Invoke-RestMethod -Uri "$BASE_URL/api/chat" -Method POST `
             -Body $body -ContentType "application/json" -TimeoutSec 60
        Write-Host ($r.reply ?? $r.error ?? ($r | ConvertTo-Json))
    } catch {
        Write-Host "[error] $($_.Exception.Message)" -ForegroundColor Red
    }
}

function Get-Status {
    try {
        $r = Invoke-RestMethod -Uri "$BASE_URL/health" -TimeoutSec 5
        Write-Host "✅ AI Agent is running at $BASE_URL" -ForegroundColor Green
        $r | ConvertTo-Json | Write-Host
    } catch {
        Write-Host "❌ AI Agent is not reachable at $BASE_URL" -ForegroundColor Red
        Write-Host "   Start with: scripts\start.bat" -ForegroundColor Yellow
    }
}

function Show-Help {
    Write-Host @"

ai — AI Agent CLI (Windows)

USAGE:
  ai "task description"     Run a task (with tool use)
  ai task "task"            Same as above
  ai chat "message"         Single-turn chat
  ai status                 Check if the server is running
  ai help                   Show this help

EXAMPLES:
  ai "List all Python files in C:\Projects"
  ai "Write a script to rename all .txt files to .md"
  ai chat "What is the difference between RAG and fine-tuning?"
  ai status

ENVIRONMENT:
  AI_AGENT_URL    Override server URL (default: http://localhost:5000)

"@ -ForegroundColor Cyan
}

# ── Dispatch ──────────────────────────────────────────────────────────────────
switch ($Command.ToLower()) {
    { $_ -in "chat" } {
        $msg = $Args -join " "
        if (-not $msg) { Write-Host "Usage: ai chat `"message`"" -ForegroundColor Yellow; exit 1 }
        Invoke-Chat $msg
    }
    { $_ -in "status" } { Get-Status }
    { $_ -in "help", "-h", "--help" } { Show-Help }
    { $_ -in "task", "run" } {
        $task = $Args -join " "
        if (-not $task) { Write-Host "Usage: ai task `"description`"" -ForegroundColor Yellow; exit 1 }
        Invoke-Task $task
    }
    default {
        # Treat everything as a task
        $task = (@($Command) + $Args) -join " "
        if (-not $task.Trim()) { Show-Help; exit 0 }
        Invoke-Task $task
    }
}

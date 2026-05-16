@echo off
title AI Agent
cd /d "%~dp0.."
if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
) else (
    echo [!] Virtual environment not found. Run setup.ps1 first.
    pause
    exit /b 1
)
echo [*] Starting AI Agent...
echo [*] Dashboard: http://localhost:5000
python orchestrator.py serve
pause

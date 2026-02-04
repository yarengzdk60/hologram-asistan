$ErrorActionPreference = "Stop"

# Ensure script is run from the project root
$scriptPath = $MyInvocation.MyCommand.Path
$projectRoot = Split-Path $scriptPath -Parent
Set-Location $projectRoot

# Define path to venv python
$pythonPath = Join-Path $projectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $pythonPath)) {
    Write-Host "❌ Virtual environment not found!" -ForegroundColor Red
    Write-Host "💡 Please run: .\install_dependencies.ps1" -ForegroundColor Yellow
    exit 1
}

Write-Host "🚀 Starting Hologram Assistant Server..." -ForegroundColor Cyan

# Set PYTHONPATH to project root
$env:PYTHONPATH = $projectRoot

# Set HuggingFace API Key
$env:HUGGINGFACE_API_KEY = "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"

# Run the server
& $pythonPath server/main.py

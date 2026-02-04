$ErrorActionPreference = "Stop"

# Ensure script is run from the project root
$scriptPath = $MyInvocation.MyCommand.Path
$projectRoot = Split-Path $scriptPath -Parent
Set-Location $projectRoot

# Define path to venv python
$pythonPath = Join-Path $projectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $pythonPath)) {
    Write-Host "Virtual environment not found!" -ForegroundColor Red
    Write-Host "Please run: .\install_dependencies.ps1" -ForegroundColor Yellow
    exit 1
}

Write-Host " Starting Hologram Assistant Server..." -ForegroundColor Cyan

# Set PYTHONPATH to project root
$env:PYTHONPATH = $projectRoot

# Set Google Gemini API Key (Get from https://aistudio.google.com/apikey)
$env:GOOGLE_API_KEY = "AIzaSyBgUUS8KMnQn5ROWzbgXCFTx9Fdxi8KwYQ"

# Run the server
& $pythonPath server/main.py

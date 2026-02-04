$ErrorActionPreference = "Stop"

# Ensure script is run from the project root
$scriptPath = $MyInvocation.MyCommand.Path
$projectRoot = Split-Path $scriptPath -Parent
Set-Location $projectRoot

Write-Host "📦 Installing dependencies..." -ForegroundColor Cyan

# Check if venv exists, if not create it
$venvPath = Join-Path $projectRoot ".venv"
$pythonPath = Join-Path $venvPath "Scripts\python.exe"
$pipPath = Join-Path $venvPath "Scripts\pip.exe"

if (-not (Test-Path $pythonPath)) {
    Write-Host "🔧 Creating virtual environment..." -ForegroundColor Yellow
    python -m venv .venv
    
    if (-not (Test-Path $pythonPath)) {
        Write-Error "Failed to create virtual environment"
        exit 1
    }
}

Write-Host "✅ Virtual environment found" -ForegroundColor Green

# Upgrade pip first
Write-Host "⬆️ Upgrading pip..." -ForegroundColor Yellow
& $pythonPath -m pip install --upgrade pip

# Install requirements
Write-Host "📥 Installing packages from requirements.txt..." -ForegroundColor Yellow
& $pipPath install -r requirements.txt

if ($LASTEXITCODE -eq 0) {
    Write-Host "✅ All dependencies installed successfully!" -ForegroundColor Green
} else {
    Write-Error "Failed to install dependencies"
    exit 1
}

#!/usr/bin/env powershell
# Start server script - ensures clean startup on port 8000

param(
    [int]$Port = 8000
)

Write-Host "Starting Invoice OCR server on port $Port..." -ForegroundColor Green

# Kill any existing uvicorn processes on this port
$processes = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue | 
    Select-Object -ExpandProperty OwningProcess -Unique

foreach ($pid in $processes) {
    try {
        $proc = Get-Process -Id $pid -ErrorAction SilentlyContinue
        if ($proc -and $proc.ProcessName -like "*uvicorn*") {
            Write-Host "Killing existing uvicorn process (PID: $pid)" -ForegroundColor Yellow
            Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue
        }
    } catch {
        Write-Host "Could not kill process $pid" -ForegroundColor Red
    }
}

# Wait for port to be released
Start-Sleep -Seconds 2

# Activate venv and start server
$venvPath = Join-Path $PSScriptRoot "venv\Scripts\Activate.ps1"
if (Test-Path $venvPath) {
    & $venvPath
    Write-Host "Virtual environment activated" -ForegroundColor Green
} else {
    Write-Host "Virtual environment not found at $venvPath" -ForegroundColor Red
    exit 1
}

# Start uvicorn
Write-Host "Starting uvicorn on port $Port..." -ForegroundColor Green
uvicorn app.main:app --host 0.0.0.0 --port $Port --reload
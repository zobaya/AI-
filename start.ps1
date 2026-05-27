# One-click start all services (Backend + AI Service + Frontend)
# Usage: .\start.ps1
# Press Ctrl+C to stop all services

$ErrorActionPreference = "Stop"
$ROOT_DIR = $PSScriptRoot
$jobs = @()

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "  AI System - Start All Services" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""

# 1. Backend (Django)
if (-not (Test-Path "$ROOT_DIR\backend\.env")) {
    Write-Host "[WARN] Backend missing .env, copy from .env.example first" -ForegroundColor Yellow
    exit 1
}
Write-Host "[START] Backend (Django :8000)..." -ForegroundColor Green
$jobs += Start-Job -ScriptBlock {
    Set-Location "$using:ROOT_DIR\backend"
    uv run python manage.py runserver 8000 2>&1
}

# 2. AI Service (FastAPI)
if (-not (Test-Path "$ROOT_DIR\ai-service\.env")) {
    Write-Host "[WARN] AI Service missing .env, copy from .env.example first" -ForegroundColor Yellow
    exit 1
}
Write-Host "[START] AI Service API (FastAPI :7729)..." -ForegroundColor Green
$jobs += Start-Job -ScriptBlock {
    Set-Location "$using:ROOT_DIR\ai-service"
    uv run python main.py 2>&1
}

# 3. Celery Worker
Write-Host "[START] Celery Worker..." -ForegroundColor Green
$jobs += Start-Job -ScriptBlock {
    Set-Location "$using:ROOT_DIR\ai-service"
    uv run python worker.py 2>&1
}

# 4. Frontend (Vite)
Write-Host "[START] Frontend (Vite :5173)..." -ForegroundColor Green
$jobs += Start-Job -ScriptBlock {
    Set-Location "$using:ROOT_DIR\frontend"
    npm run dev 2>&1
}

Write-Host ""
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "  All services started" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Frontend :  http://localhost:5173"
Write-Host "  Backend  :  http://localhost:8000"
Write-Host "  AI API   :  http://localhost:7729"
Write-Host ""
Write-Host "  Press Ctrl+C to stop all services" -ForegroundColor Yellow
Write-Host ""

try {
    while ($true) {
        foreach ($job in $jobs) {
            $output = Receive-Job -Job $job -ErrorAction SilentlyContinue 2>$null
            if ($output) {
                foreach ($line in $output) {
                    Write-Host "[$($job.Id)] $line"
                }
            }
        }
        Start-Sleep -Seconds 1
    }
} finally {
    Write-Host ""
    Write-Host "[INFO] Stopping all services..." -ForegroundColor Cyan
    $jobs | Stop-Job -PassThru | Remove-Job
    Write-Host "[INFO] All services stopped" -ForegroundColor Cyan
}

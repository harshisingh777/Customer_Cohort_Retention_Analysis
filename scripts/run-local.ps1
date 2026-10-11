# One-step local start on Windows: secrets, containers, real data.
#   powershell -ExecutionPolicy Bypass -File scripts\run-local.ps1            # first run (loads Online Retail II)
#   powershell -ExecutionPolicy Bypass -File scripts\run-local.ps1 -SkipSeed  # later runs
param([switch]$SkipSeed)
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

docker info *> $null
if ($LASTEXITCODE -ne 0) { throw "Docker Desktop is not running. Start it, wait for 'Engine running', then retry." }

& "$PSScriptRoot\init-env.ps1"

$compose = @("compose", "-f", "infra/docker-compose.yml")
docker @compose up -d --build
if ($LASTEXITCODE -ne 0) { throw "docker compose up failed" }

if (-not $SkipSeed) {
    Write-Host "Loading Online Retail II (downloads 45 MB on first run, about 4-5 minutes)..."
    docker @compose run --rm worker python -m pipeline.ingest seed retail
    if ($LASTEXITCODE -ne 0) { throw "seeding failed - see the output above" }
}

Write-Host ""
Write-Host "Dashboard: http://localhost:3000  (Development sign-in: admin@example.com)"
Write-Host "API docs:  http://localhost:8000/docs"

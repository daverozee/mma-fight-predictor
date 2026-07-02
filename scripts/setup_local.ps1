param(
    [switch]$SkipBuild,
    [switch]$SkipImport
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $root

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker is required. Install Docker Desktop, then rerun this script."
}

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "Created .env from .env.example. Add optional API keys there when available."
}

if ($SkipBuild) {
    docker compose up -d
} else {
    docker compose up -d --build
}

if (-not $SkipImport) {
    docker compose exec -T web python scripts/import_data.py
    docker compose exec -T web python scripts/train_model.py
}

Write-Host ""
Write-Host "MMA Fight Predictor is running:"
Write-Host "  http://127.0.0.1:8000"
Write-Host ""
Write-Host "Useful commands:"
Write-Host "  docker compose logs -f web"
Write-Host "  docker compose logs -f worker"
Write-Host "  py -3 -m pytest"
Write-Host "  py -3 -m ruff check ."

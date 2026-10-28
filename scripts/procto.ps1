<#
.SYNOPSIS
  Procto Windows task runner (PowerShell equivalent of the Makefile).

.EXAMPLE
  ./scripts/procto.ps1 setup
  ./scripts/procto.ps1 dev
  ./scripts/procto.ps1 check
  ./scripts/procto.ps1 infra up
  ./scripts/procto.ps1 db upgrade
#>
[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet("setup", "dev", "dev-backend", "dev-frontend", "check", "test",
        "lint", "typecheck", "fmt", "infra", "db", "help")]
    [string]$Command = "help",

    [Parameter(Position = 1)]
    [string]$Sub = "",

    [Parameter(Position = 2)]
    [string]$Message = ""
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot

function Invoke-Step($Label, $WorkDir, [scriptblock]$Block) {
    Write-Host "==> $Label" -ForegroundColor Cyan
    Push-Location $WorkDir
    try { & $Block } finally { Pop-Location }
}

switch ($Command) {
    "help" {
        Write-Host @"
Procto commands:
  setup         install deps (backend + frontend) and run migrations
  dev           start backend :8001 and frontend :3001 (two windows, hot reload)
  dev-backend   start FastAPI only
  dev-frontend  start Next.js only
  check         lint + typecheck + tests (both sides)
  test          run all tests
  lint          run linters + format check
  typecheck     run type checkers
  fmt           auto-fix formatting
  infra up|down manage Docker infrastructure (postgres, redis, livekit, minio)
  db upgrade|revision [msg]   run Alembic migrations
"@
    }

    "setup" {
        if (-not (Test-Path "$Root\.env")) {
            Copy-Item "$Root\.env.example" "$Root\.env"
            Write-Host "==> created .env from .env.example"
        }
        Invoke-Step "backend: uv sync" "$Root\backend" { uv sync }
        Invoke-Step "frontend: npm install" "$Root\frontend" { npm install }
        Invoke-Step "backend: migrations" "$Root\backend" { uv run alembic upgrade head }
    }

    "dev-backend" {
        Invoke-Step "backend: uvicorn :8001" "$Root\backend" {
            uv run uvicorn app.main:app --reload --port 8001
        }
    }

    "dev-frontend" {
        Invoke-Step "frontend: next dev :3001" "$Root\frontend" { npm run dev }
    }

    "dev" {
        Write-Host "Starting backend and frontend in separate windows..." -ForegroundColor Cyan
        Start-Process powershell -ArgumentList "-NoExit", "-Command",
            "Set-Location '$Root'; ./scripts/procto.ps1 dev-backend"
        Start-Process powershell -ArgumentList "-NoExit", "-Command",
            "Set-Location '$Root'; ./scripts/procto.ps1 dev-frontend"
        Write-Host "backend  -> http://localhost:8001/api/health" -ForegroundColor Green
        Write-Host "frontend -> http://localhost:3001" -ForegroundColor Green
    }

    "lint" {
        Invoke-Step "backend: ruff" "$Root\backend" {
            uv run ruff check .
            if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
            uv run ruff format --check .
            if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        }
        Invoke-Step "frontend: eslint + prettier" "$Root\frontend" {
            npm run lint
            if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
            npm run format:check
            if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        }
    }

    "typecheck" {
        Invoke-Step "backend: mypy" "$Root\backend" {
            uv run mypy app tests
            if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        }
        Invoke-Step "frontend: tsc" "$Root\frontend" {
            npm run typecheck
            if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        }
    }

    "test" {
        Invoke-Step "backend: pytest" "$Root\backend" {
            uv run pytest
            if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        }
        Invoke-Step "frontend: vitest" "$Root\frontend" {
            npm run test
            if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        }
    }

    "check" {
        & $PSCommandPath lint
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        & $PSCommandPath typecheck
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        & $PSCommandPath test
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        Write-Host "All checks passed." -ForegroundColor Green
    }

    "fmt" {
        Invoke-Step "backend: ruff fix" "$Root\backend" {
            uv run ruff check --fix .
            uv run ruff format .
        }
        Invoke-Step "frontend: prettier" "$Root\frontend" { npm run format }
    }

    "infra" {
        switch ($Sub) {
            "up" {
                Push-Location $Root
                try { docker compose up -d } finally { Pop-Location }
            }
            "down" {
                # Stops containers only — volumes (data) are kept.
                Push-Location $Root
                try { docker compose stop } finally { Pop-Location }
            }
            default { Write-Host "usage: procto.ps1 infra up|down" -ForegroundColor Yellow }
        }
    }

    "db" {
        switch ($Sub) {
            "upgrade" {
                Invoke-Step "backend: alembic upgrade head" "$Root\backend" {
                    uv run alembic upgrade head
                }
            }
            "revision" {
                if (-not $Message) { Write-Host "usage: procto.ps1 db revision <message>" -ForegroundColor Yellow; break }
                Invoke-Step "backend: alembic revision" "$Root\backend" {
                    uv run alembic revision --autogenerate -m "$Message"
                }
            }
            default { Write-Host "usage: procto.ps1 db upgrade|revision <message>" -ForegroundColor Yellow }
        }
    }
}

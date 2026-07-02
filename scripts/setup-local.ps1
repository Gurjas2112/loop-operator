# One-shot local setup for Loop on Windows (Docker + Lemma stack + pod import + seed).
#
# Prerequisites (once):
#   - Docker Desktop
#   - uv + lemma-terminal:  uv tool install lemma-terminal
#   - lemma-stack:          uv tool install "git+https://github.com/lemma-work/lemma-platform.git#subdirectory=lemma-stack"
#   - Ollama with qwen2.5:3b-instruct (optional, for local LLM)
#
# Usage (PowerShell, from repo root):
#   .\scripts\setup-local.ps1
#   .\scripts\setup-local.ps1 -SkipImport    # stack already up, only seed
#   .\scripts\setup-local.ps1 -SkipSeed

param(
    [switch]$SkipImport,
    [switch]$SkipSeed,
    [switch]$OpenBoard
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

$env:PATH = "$env:USERPROFILE\.local\bin;$env:PATH"
$env:GIT_CONFIG_COUNT = "1"
$env:GIT_CONFIG_KEY_0 = "core.longpaths"
$env:GIT_CONFIG_VALUE_0 = "true"

function Ensure-Docker {
    try {
        if (docker info --format "{{.ServerVersion}}" 2>$null) { return }
    } catch {}
    $exe = "${env:ProgramFiles}\Docker\Docker\Docker Desktop.exe"
    if (Test-Path $exe) {
        Write-Host "Starting Docker Desktop..."
        Start-Process $exe
        $deadline = (Get-Date).AddMinutes(3)
        while ((Get-Date) -lt $deadline) {
            Start-Sleep -Seconds 5
            if (docker info --format "{{.ServerVersion}}" 2>$null) { return }
        }
    }
    throw "Docker is not running."
}

function Ensure-Stack {
    if (-not (Test-Path "$env:USERPROFILE\.lemma\local\config.toml")) {
        Write-Host "Installing Lemma stack (first time — pulls images)..."
        lemma-stack install --runtime docker -y | Out-Host
    } else {
        lemma-stack start | Out-Host
    }

    # Windows: agentbox nested docker mounts need Docker Desktop host path form.
    $drive = $env:USERPROFILE.Substring(0, 1).ToLower()
    $rest = $env:USERPROFILE.Substring(3).Replace('\', '/')
    $hostRoot = "/run/desktop/mnt/host/$drive/$rest/.lemma/local/data/workspaces"
    $current = lemma-stack config get agentbox.env.AGENTBOX_STORAGE_HOST_ROOT 2>$null
    if ($current -notmatch "/run/desktop/mnt/host/") {
        lemma-stack config set agentbox.env.AGENTBOX_STORAGE_HOST_ROOT $hostRoot | Out-Host
    }

    # Local open model via Ollama (skip if Ollama not running).
    try {
        $null = Invoke-WebRequest -UseBasicParsing -Uri "http://localhost:11434/api/version" -TimeoutSec 3
        lemma-stack config set LEMMA_DEFAULT_MODEL_TYPE openai_compat | Out-Null
        lemma-stack config set LEMMA_OPENAI_API_KEY ollama-local | Out-Null
        lemma-stack config set LEMMA_OPENAI_BASE_URL "http://host.docker.internal:11434/v1" | Out-Null
        lemma-stack config set LEMMA_OPENAI_DEFAULT_MODEL "qwen2.5:3b-instruct" | Out-Null
        lemma-stack config set LEMMA_OPENAI_MODEL_NAMES "qwen2.5:3b-instruct,llama3.2:latest" | Out-Null
        lemma-stack restart | Out-Host
    } catch {
        Write-Host "Ollama not detected — agents will use stack default model settings."
    }
}

function Ensure-Auth {
    lemma servers select local | Out-Null
    $status = lemma auth status 2>&1 | Out-String
    if ($status -match "Missing token") {
        Write-Host ""
        Write-Host "Sign in required. Opening http://127-0-0-1.sslip.io:3711 ..."
        Start-Process "http://127-0-0-1.sslip.io:3711"
        Write-Host "Create/sign in to your Lemma account, then press Enter here."
        Read-Host
        lemma auth login --no-init | Out-Host
    }
}

function Ensure-Pod {
    $orgs = lemma orgs list --json 2>&1 | ConvertFrom-Json
    $org = $orgs | Select-Object -First 1
    if (-not $org) {
        $org = lemma orgs create "Loop" --json | ConvertFrom-Json
    }
    $env:LEMMA_ORG_ID = $org.id

    $pods = lemma pods list --json 2>&1 | ConvertFrom-Json
    $pod = $pods | Where-Object { $_.name -eq "loop" } | Select-Object -First 1
    if (-not $pod) {
        $pod = lemma pods create loop --org $org.id --description "AI Meeting-to-Execution Operator" --json | ConvertFrom-Json
    }
    $env:LEMMA_POD_ID = $pod.id
    Write-Host "Org: $($org.name)  Pod: $($pod.name)"
}

Ensure-Docker
Ensure-Stack
Ensure-Auth
Ensure-Pod

if (-not $SkipImport) {
    Write-Host "Importing ./loop bundle (Slack surface skipped if placeholder account_id)..."
    lemma pods import ./loop --dry-run | Out-Host
    lemma pods import ./loop 2>&1 | Out-Host
}

if (-not $SkipSeed) {
    Write-Host "Seeding demo data..."
    python seed/seed_local.py
}

Write-Host ""
Write-Host "Local Execution Board: http://execution-board.127-0-0-1.sslip.io:8711"
Write-Host "Public URL:            .\scripts\host-live.ps1 -OpenBrowser"

if ($OpenBoard) {
    Start-Process "http://execution-board.127-0-0-1.sslip.io:8711"
}

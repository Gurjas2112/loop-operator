# Expose the local Loop Execution Board on a public HTTPS URL (Cloudflare quick tunnel).
# Requires: Docker running, lemma-stack up, cloudflared on PATH.
#
# Usage (PowerShell, from repo root):
#   .\scripts\host-live.ps1
#   .\scripts\host-live.ps1 -OpenBrowser
#
# Writes:
#   .live-url.txt          — public Execution Board URL
#   .live-auth-url.txt     — public Lemma frontend URL (sign-in / org setup)
#   scripts/LIVE_URL.md    — human-readable summary

param(
    [switch]$OpenBrowser
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

$env:PATH = "$env:USERPROFILE\.local\bin;$env:PATH"

function Ensure-Docker {
    try {
        $v = docker info --format "{{.ServerVersion}}" 2>$null
        if ($v) { Write-Host "Docker: $v"; return }
    } catch {}
    $exe = "${env:ProgramFiles}\Docker\Docker\Docker Desktop.exe"
    if (Test-Path $exe) {
        Write-Host "Starting Docker Desktop..."
        Start-Process $exe
        $deadline = (Get-Date).AddMinutes(3)
        while ((Get-Date) -lt $deadline) {
            Start-Sleep -Seconds 5
            try {
                $v = docker info --format "{{.ServerVersion}}" 2>$null
                if ($v) { Write-Host "Docker ready: $v"; return }
            } catch {}
        }
    }
    throw "Docker is not running. Start Docker Desktop and re-run this script."
}

function Ensure-Stack {
    Write-Host "Starting Lemma stack..."
    lemma-stack start | Out-Host
    $status = lemma-stack status 2>&1 | Out-String
    if ($status -notmatch "running") {
        throw "Lemma stack did not start cleanly. Run: lemma-stack status"
    }
}

function Stop-OldTunnels {
    Get-CimInstance Win32_Process -Filter "Name='cloudflared.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -match "127\.0\.0\.1:(8711|3711)" } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
}

function Start-Tunnel {
    param(
        [string]$Name,
        [string]$LocalUrl,
        [string]$HostHeader,
        [string]$OutFile
    )
    $log = Join-Path $RepoRoot ".cloudflared-$Name.log"
    if (Test-Path $log) { Remove-Item $log -Force }

    $args = @(
        "tunnel",
        "--no-autoupdate",
        "--url", $LocalUrl,
        "--http-host-header", $HostHeader
    )
    Write-Host "Starting tunnel '$Name' -> $LocalUrl (Host: $HostHeader)"
    Start-Process -FilePath "cloudflared" -ArgumentList $args -WindowStyle Hidden -RedirectStandardError $log

    $deadline = (Get-Date).AddSeconds(60)
    $publicUrl = $null
    while ((Get-Date) -lt $deadline) {
        Start-Sleep -Seconds 2
        if (Test-Path $log) {
            $text = Get-Content $log -Raw -ErrorAction SilentlyContinue
            if ($text -match "(https://[a-z0-9-]+\.trycloudflare\.com)") {
                $publicUrl = $Matches[1]
                break
            }
        }
    }
    if (-not $publicUrl) {
        throw "Timed out waiting for cloudflared public URL ($Name). See $log"
    }
    Set-Content -Path $OutFile -Value $publicUrl -Encoding utf8
    Write-Host "  Public URL: $publicUrl"
    return $publicUrl
}

Ensure-Docker
Ensure-Stack
Stop-OldTunnels

# Backend serves the Execution Board app (subdomain routing on port 8711).
$boardUrl = Start-Tunnel -Name "board" `
    -LocalUrl "http://127.0.0.1:8711" `
    -HostHeader "execution-board.127-0-0-1.sslip.io" `
    -OutFile (Join-Path $RepoRoot ".live-url.txt")

# Frontend for Lemma platform sign-in (needed once per browser for SDK session).
$authUrl = Start-Tunnel -Name "auth" `
    -LocalUrl "http://127.0.0.1:3711" `
    -HostHeader "127-0-0-1.sslip.io" `
    -OutFile (Join-Path $RepoRoot ".live-auth-url.txt")

$md = @"
# Loop — live public URLs

Generated: $(Get-Date -Format "yyyy-MM-dd HH:mm:ss")

| Surface | URL |
| ------- | --- |
| **Execution Board** | $boardUrl |
| **Lemma sign-in** (first visit) | $authUrl |

## How to use (share with reviewers)

1. Open **Lemma sign-in** once and log in with your Lemma account (or sign up).
2. Open the **Execution Board** link.
3. Use the app demo login:
   - Admin: ``admin@loop.demo`` / ``loop-admin``
   - User: ``user@loop.demo`` / ``loop-user``

## Notes

- Tunnels stay up while ``cloudflared`` processes run. Re-run ``.\scripts\host-live.ps1`` after reboot.
- Local URLs still work: ``http://execution-board.127-0-0-1.sslip.io:8711``
- Stop tunnels: ``Get-Process cloudflared | Stop-Process``
"@
Set-Content -Path (Join-Path $RepoRoot "scripts\LIVE_URL.md") -Value $md -Encoding utf8

Write-Host ""
Write-Host "=== LIVE ===" -ForegroundColor Green
Write-Host "Execution Board: $boardUrl"
Write-Host "Lemma sign-in:   $authUrl"
Write-Host "Details: scripts/LIVE_URL.md"

if ($OpenBrowser) {
    Start-Process $authUrl
    Start-Sleep -Seconds 2
    Start-Process $boardUrl
}

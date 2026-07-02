# Public live link (Cloudflare quick tunnel)

Loop runs locally on Lemma. To share a **public HTTPS URL** with reviewers (no VPN, no localhost), expose the stack with [Cloudflare Tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/do-more-with-tunnels/trycloudflare/) (`cloudflared`).

## Prerequisites

- Docker Desktop running
- Lemma stack up (`lemma-stack start`)
- `cloudflared` on PATH ([install](https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/install-and-setup/installation/))

## One command (Windows)

```powershell
.\scripts\host-live.ps1 -OpenBrowser
```

This script:

1. Ensures Docker + Lemma stack are running
2. Starts **two** quick tunnels:
   - **Execution Board** → local backend `:8711` with Host `execution-board.127-0-0-1.sslip.io`
   - **Lemma sign-in** → local frontend `:3711` with Host `127-0-0-1.sslip.io`
3. Writes URLs to:
   - `.live-url.txt` — share this for the board
   - `.live-auth-url.txt` — open once to sign in to Lemma (SDK session)
   - `scripts/LIVE_URL.md` — summary for humans

## Share flow

1. Send reviewers **Lemma sign-in** URL → they create/sign in once (Lemma platform account).
2. Send **Execution Board** URL → they use demo app login:
   - Admin: `admin@loop.demo` / `loop-admin`
   - User: `user@loop.demo` / `loop-user`

## Manual (any OS)

```bash
# Execution Board (backend app host)
cloudflared tunnel --url http://127.0.0.1:8711 \
  --http-host-header execution-board.127-0-0-1.sslip.io

# Lemma auth frontend (separate terminal)
cloudflared tunnel --url http://127.0.0.1:3711 \
  --http-host-header 127-0-0-1.sslip.io
```

Copy the `https://….trycloudflare.com` URL from each process’s log line.

## Stop tunnels

```powershell
Get-Process cloudflared -ErrorAction SilentlyContinue | Stop-Process
```

## Limitations

- Quick tunnel URLs **change every restart** — re-run `host-live.ps1` and share the new links.
- For a **stable domain**, use a named Cloudflare tunnel + your own hostname (Cloudflare account required).
- Slack notifications still need connector setup (`scripts/setup-slack.md`).

## Full local setup from scratch

```powershell
.\scripts\setup-local.ps1 -OpenBoard
.\scripts\host-live.ps1 -OpenBrowser
```

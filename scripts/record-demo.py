#!/usr/bin/env python3
"""Record the Loop demo walkthrough to essential_docs/loop-demo.mp4.

A browser-automation "web browser agent": it VERIFIES the stack is healthy, then
drives the live Execution Board with Playwright while recording, then transcodes
the WebM to a portable H.264 MP4.

Auth: the board is served from a subdomain (execution-board.127-0-0-1.sslip.io)
while the Lemma front-token cookie is host-only on the bare frontend host, so the
board's SDK can't see the session and would bounce to sign-in. We reuse the Lemma
session persisted in a dedicated browser profile and mirror the front-token cookie
onto the board subdomain — deterministic, no manual login during recording.

If the profile has no Lemma session yet, run once (headed) to establish it:
    python scripts/record-demo.py --login      # opens a window; sign in once

Then record:
    python scripts/record-demo.py

Env: FFMPEG (path override), BOARD_URL (override board URL).
"""
import os
import pathlib
import shutil
import subprocess
import sys
import time
import urllib.request

REPO = pathlib.Path(__file__).resolve().parents[1]
OUT_MP4 = REPO / "essential_docs" / "loop-demo.mp4"
SCRATCH = pathlib.Path(os.environ.get("TEMP", str(REPO))) / "loop-demo-record"
PROFILE = SCRATCH / "profile"
VIDEO_DIR = SCRATCH / "video"

BOARD_URL = os.environ.get("BOARD_URL", "http://execution-board.127-0-0-1.sslip.io:8711")
BOARD_HOST = "execution-board.127-0-0-1.sslip.io"
FRONTEND = "http://127-0-0-1.sslip.io:3711"
ADMIN_EMAIL, ADMIN_PW = "admin@loop.demo", "loop-admin"
SESS_KEY = "loop.auth.session.v1"
VW, VH = 1440, 810


def log(m):
    print(f"[record-demo] {m}", flush=True)


def safe(fn, default=None):
    try:
        return fn()
    except Exception:
        return default


def http_ok(url, timeout=12):
    try:
        with urllib.request.urlopen(urllib.request.Request(url), timeout=timeout) as r:
            return 200 <= r.status < 400
    except Exception:
        return False


def preflight():
    log("PRE-FLIGHT verification")
    checks = []
    try:
        out = subprocess.run(["docker", "ps", "--format", "{{.Names}}"],
                             capture_output=True, text=True, timeout=30).stdout
        n = len([x for x in out.splitlines() if x.startswith("lemma-local-")])
        checks.append((f"lemma containers running ({n}/6)", n >= 6))
    except Exception as e:
        checks.append((f"docker ps ({e})", False))
    checks.append(("board responds (200)", http_ok(BOARD_URL)))
    checks.append(("ollama responds (200)", http_ok("http://localhost:11434/api/version")))
    ok = True
    for name, passed in checks:
        log(f"  [{'OK ' if passed else 'FAIL'}] {name}")
        ok = ok and passed
    if not ok:
        log("Pre-flight FAILED — start the stack (lemma-stack start) and retry.")
        sys.exit(2)
    log("Pre-flight PASSED — everything works.\n")


def has_session(pw):
    ctx = pw.chromium.launch_persistent_context(str(PROFILE), headless=True)
    try:
        return any(c["name"] == "sFrontToken" for c in ctx.cookies())
    finally:
        ctx.close()


def do_login(pw):
    """One-time interactive Lemma login to seed the profile session."""
    log("Opening a browser window — sign in to Lemma once, then the window closes.")
    ctx = pw.chromium.launch_persistent_context(
        str(PROFILE), headless=False, viewport={"width": VW, "height": VH})
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    safe(lambda: page.goto(FRONTEND + "/auth", wait_until="domcontentloaded"))
    deadline = time.time() + 360
    while time.time() < deadline:
        if any(c["name"] == "sFrontToken" for c in ctx.cookies()):
            safe(lambda: page.click("button:has-text('Continue')", timeout=1500))
            time.sleep(2)
            break
        time.sleep(2)
    got = any(c["name"] == "sFrontToken" for c in ctx.cookies())
    ctx.close()
    if not got:
        log("No session established. Re-run: python scripts/record-demo.py --login")
        sys.exit(3)
    log("Session established.\n")


def mirror_cookies(ctx):
    """Copy host-only frontend session cookies onto the board subdomain."""
    add = []
    for c in ctx.cookies():
        if c["name"] in ("sFrontToken", "st-last-access-token-update") and "execution-board" not in c["domain"]:
            add.append({"name": c["name"], "value": c["value"], "domain": BOARD_HOST, "path": "/",
                        "httpOnly": c.get("httpOnly", False), "secure": False,
                        "sameSite": c.get("sameSite", "Lax")})
    if add:
        ctx.add_cookies(add)
    return [a["name"] for a in add]


CAPTION_JS = r"""(text) => {
  let el = document.getElementById('__cap');
  if (!el) {
    el = document.createElement('div'); el.id = '__cap';
    el.style.cssText = 'position:fixed;left:50%;bottom:34px;transform:translateX(-50%);'
      + 'z-index:2147483647;background:rgba(14,17,22,.94);color:#E7ECF3;'
      + 'font:600 21px/1.4 Inter,Segoe UI,sans-serif;padding:13px 24px;border-radius:12px;'
      + 'border:1px solid #3DD9B0;box-shadow:0 10px 44px rgba(0,0,0,.55);max-width:82vw;'
      + 'text-align:center;letter-spacing:.2px;';
    (document.body || document.documentElement).appendChild(el);
  }
  el.textContent = text;
}"""


def caption(page, text, hold=3.5):
    safe(lambda: page.evaluate(CAPTION_JS, text))
    page.wait_for_timeout(int(hold * 1000))


def scroll_to(page, selector):
    safe(lambda: page.evaluate(
        "s => { const e = document.querySelector(s); if (e) e.scrollIntoView({block:'center', behavior:'smooth'}); }",
        selector))


def record(pw):
    log("Recording walkthrough (headless)...")
    if VIDEO_DIR.exists():
        shutil.rmtree(VIDEO_DIR, ignore_errors=True)
    VIDEO_DIR.mkdir(parents=True, exist_ok=True)
    ctx = pw.chromium.launch_persistent_context(
        str(PROFILE), headless=True, viewport={"width": VW, "height": VH},
        record_video_dir=str(VIDEO_DIR), record_video_size={"width": VW, "height": VH})
    log(f"  mirrored cookies: {mirror_cookies(ctx)}")
    page = ctx.pages[0] if ctx.pages else ctx.new_page()

    # Load board, reset ONLY the app-gate session so the login shows on camera.
    safe(lambda: page.goto(BOARD_URL, wait_until="domcontentloaded"))
    page.wait_for_timeout(1200)
    safe(lambda: page.evaluate(f"localStorage.removeItem('{SESS_KEY}')"))
    safe(lambda: page.reload(wait_until="domcontentloaded"))

    caption(page, "Loop — the operator that owns meeting follow-through", 3.2)
    safe(lambda: page.wait_for_selector("#auth-form", timeout=15000))
    caption(page, "Sign in — approvals are role-gated (admin vs main user)", 3.2)
    row = safe(lambda: page.query_selector(".demo-row[data-em='admin@loop.demo']"))
    if row:
        safe(lambda: row.click()); page.wait_for_timeout(900)
    else:
        safe(lambda: page.fill("#a-email", ADMIN_EMAIL)); safe(lambda: page.fill("#a-pass", ADMIN_PW))
    page.wait_for_timeout(600)
    safe(lambda: page.click("#auth-submit"))

    if not safe(lambda: page.wait_for_selector("#board .card", timeout=30000)):
        log("  Board did not render — is the Lemma session valid? Try --login."); ctx.close(); sys.exit(4)
    page.wait_for_timeout(1200)

    caption(page, "A live situation room for commitments coming due", 4.0)
    caption(page, "Overdue · Due today · Open — counted live", 3.6)

    scroll_to(page, "#horizon")
    caption(page, "Deadline Horizon — items drift toward NOW; overdue glows red", 4.6)

    scroll_to(page, "#board")
    caption(page, "Swimlanes by status, cards colored by risk", 4.0)

    scroll_to(page, "#approvals")
    caption(page, "Approvals inbox — risky items gated behind a human FORM", 4.4)

    # Provenance drawer — click the first card.
    scroll_to(page, "#board")
    page.wait_for_timeout(500)
    card = safe(lambda: page.query_selector("#board .card"))
    if card:
        safe(lambda: card.click())
        if safe(lambda: page.wait_for_selector("#drawer.open", timeout=8000)):
            page.wait_for_timeout(700)
            caption(page, "Provenance — verbatim quote, transcript page, and what Loop remembers", 5.2)
            page.wait_for_timeout(400)
            safe(lambda: page.click("#drawer-x", timeout=3000))
            page.wait_for_timeout(500)

    scroll_to(page, "#kpis")
    caption(page, "Ops panel — metrics and a live activity feed", 4.0)

    scroll_to(page, "lemma-agent-thread")
    caption(page, "Desk — ask what's due, or what we know about an owner", 4.0)

    safe(lambda: page.evaluate("window.scrollTo({top:0,behavior:'smooth'})"))
    caption(page, "Loop — meeting in → owned, dated, gated, remembered execution", 3.6)
    page.wait_for_timeout(700)

    video_path = safe(lambda: page.video.path()) if page.video else None
    ctx.close()  # flush video
    if not video_path or not pathlib.Path(video_path).exists():
        webms = sorted(VIDEO_DIR.glob("*.webm"), key=lambda p: p.stat().st_mtime)
        video_path = str(webms[-1]) if webms else None
    if not video_path:
        log("  No video produced."); sys.exit(5)
    log(f"  WebM: {video_path}")
    return video_path


def find_ffmpeg():
    if os.environ.get("FFMPEG") and pathlib.Path(os.environ["FFMPEG"]).exists():
        return os.environ["FFMPEG"]
    p = shutil.which("ffmpeg")
    if p:
        return p
    base = pathlib.Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Packages"
    hits = list(base.glob("Gyan.FFmpeg*/**/bin/ffmpeg.exe")) if base.exists() else []
    if hits:
        return str(hits[0])
    mp = pathlib.Path(os.environ.get("LOCALAPPDATA", "")) / "ms-playwright"
    hits = list(mp.glob("ffmpeg-*/ffmpeg-win64.exe")) if mp.exists() else []
    return str(hits[0]) if hits else None


def transcode(webm):
    ff = find_ffmpeg()
    OUT_MP4.parent.mkdir(parents=True, exist_ok=True)
    if not ff:
        fallback = OUT_MP4.with_suffix(".webm")
        shutil.copy(webm, fallback)
        log(f"ffmpeg not found — saved WebM to {fallback}")
        sys.exit(6)
    log(f"Transcoding to MP4 via {ff}")
    cmd = [ff, "-y", "-i", webm, "-c:v", "libx264", "-preset", "medium", "-crf", "23",
           "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-an", str(OUT_MP4)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0 or not OUT_MP4.exists():
        log("libx264 failed; retrying default codec...")
        r2 = subprocess.run([ff, "-y", "-i", webm, "-movflags", "+faststart", str(OUT_MP4)],
                            capture_output=True, text=True)
        if r2.returncode != 0:
            log(r.stderr[-1200:]); log(r2.stderr[-1200:]); sys.exit(7)
    log(f"OK: wrote {OUT_MP4} ({OUT_MP4.stat().st_size:,} bytes)")


def main():
    login_only = "--login" in sys.argv
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        if login_only:
            do_login(pw); return
        preflight()
        if not has_session(pw):
            log("No Lemma session in profile — starting one-time login...")
            do_login(pw)
        webm = record(pw)
    transcode(webm)


if __name__ == "__main__":
    main()

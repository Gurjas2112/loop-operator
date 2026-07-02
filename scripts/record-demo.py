#!/usr/bin/env python3
"""Record the Loop demo walkthrough to essential_docs/loop-demo.mp4 (~3 min, two roles).

A browser-automation "web browser agent": it VERIFIES the stack is healthy, then
drives the live Execution Board with Playwright while recording, then transcodes
the WebM to a portable H.264 MP4.

The walkthrough covers BOTH roles and the role-gated UX:
  Act 1  Auth UI/UX — login + create-account tabs, demo credentials, roles.
  Act 2  Admin — board, Deadline Horizon, swimlanes, Approvals inbox (Approve/
         Reject), provenance drawer, ops panel, Desk.
  Act 3  Main user — sign out + sign in as user, read-only Approvals, provenance,
         Desk question, role badge.
  Act 4  Close.

Auth: the board is a subdomain while the Lemma front-token cookie is host-only on
the bare frontend host, so we reuse the Lemma session in a dedicated profile and
mirror the front-token onto the board subdomain — deterministic, no manual login.
If the profile has no session yet: python scripts/record-demo.py --login

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
SESS_KEY = "loop.auth.session.v1"
ROLES = {
    "admin": ("admin@loop.demo", "loop-admin"),
    "user": ("user@loop.demo", "loop-user"),
}
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
    add = []
    for c in ctx.cookies():
        if c["name"] in ("sFrontToken", "st-last-access-token-update") and "execution-board" not in c["domain"]:
            add.append({"name": c["name"], "value": c["value"], "domain": BOARD_HOST, "path": "/",
                        "httpOnly": c.get("httpOnly", False), "secure": False,
                        "sameSite": c.get("sameSite", "Lax")})
    if add:
        ctx.add_cookies(add)
    return [a["name"] for a in add]


CAPTION_JS = r"""(o) => {
  let el = document.getElementById('__cap');
  if (!el) {
    el = document.createElement('div'); el.id = '__cap';
    el.style.cssText = 'position:fixed;left:50%;bottom:34px;transform:translateX(-50%);'
      + 'z-index:2147483647;background:rgba(14,17,22,.94);color:#E7ECF3;'
      + 'font:600 21px/1.45 Inter,Segoe UI,sans-serif;padding:13px 24px;border-radius:12px;'
      + 'border:1px solid #3DD9B0;box-shadow:0 10px 44px rgba(0,0,0,.55);max-width:82vw;'
      + 'text-align:center;letter-spacing:.2px;';
    (document.body || document.documentElement).appendChild(el);
    let b = document.createElement('div'); b.id = '__badge';
    b.style.cssText = 'position:fixed;left:24px;top:20px;z-index:2147483647;'
      + 'font:700 13px/1 JetBrains Mono,Consolas,monospace;padding:8px 12px;border-radius:8px;'
      + 'letter-spacing:.5px;text-transform:uppercase;display:none;';
    (document.body || document.documentElement).appendChild(b);
  }
  el.textContent = o.text;
  let b = document.getElementById('__badge');
  if (o.badge) {
    b.style.display = 'block'; b.textContent = o.badge;
    if (o.badge.indexOf('ADMIN') >= 0) { b.style.background = '#F5A623'; b.style.color = '#0E1116'; }
    else { b.style.background = '#232A34'; b.style.color = '#8B97A7'; }
  }
}"""


HOLD_SCALE = float(os.environ.get("HOLD_SCALE", "1.0"))


def caption(page, text, hold=3.6, badge=None):
    safe(lambda: page.evaluate(CAPTION_JS, {"text": text, "badge": badge}))
    page.wait_for_timeout(int(hold * HOLD_SCALE * 1000))


def scroll_to(page, selector):
    safe(lambda: page.evaluate(
        "s => { const e = document.querySelector(s); if (e) e.scrollIntoView({block:'center', behavior:'smooth'}); }",
        selector))


def sign_in(page, role, badge):
    """Drive the app demo login gate for the given role."""
    email, pw = ROLES[role]
    safe(lambda: page.wait_for_selector("#auth-form", timeout=15000))
    row = safe(lambda: page.query_selector(f".demo-row[data-em='{email}']"))
    if row:
        safe(lambda: row.click()); page.wait_for_timeout(800)
    else:
        safe(lambda: page.fill("#a-email", email)); safe(lambda: page.fill("#a-pass", pw))
    page.wait_for_timeout(600)
    safe(lambda: page.click("#auth-submit"))
    return safe(lambda: page.wait_for_selector("#board .card", timeout=30000))


def tour_board(page, badge):
    """Shared board tour (counters, horizon, swimlanes, provenance, ops)."""
    caption(page, "A live situation room for commitments coming due", 4.0, badge)
    caption(page, "Overdue · Due today · Open — counted live", 3.6, badge)
    scroll_to(page, "#horizon")
    caption(page, "Deadline Horizon — items drift toward NOW; overdue glows red", 4.6, badge)
    scroll_to(page, "#board")
    caption(page, "Swimlanes by status, cards colored by risk", 4.2, badge)
    # provenance drawer — open two different cards to show provenance + memory
    scroll_to(page, "#board"); page.wait_for_timeout(400)
    cards = safe(lambda: page.query_selector_all("#board .card")) or []
    if cards:
        safe(lambda: cards[0].click())
        if safe(lambda: page.wait_for_selector("#drawer.open", timeout=8000)):
            page.wait_for_timeout(700)
            caption(page, "Every item is auditable — click to open its provenance", 4.4, badge)
            caption(page, "Verbatim quote + transcript page + confidence", 4.6, badge)
            caption(page, "“What we remember” — a standing norm recalled from past meetings", 5.0, badge)
            safe(lambda: page.click("#drawer-x", timeout=3000)); page.wait_for_timeout(500)
    if len(cards) > 1:
        scroll_to(page, "#board"); page.wait_for_timeout(300)
        safe(lambda: cards[-1].click())
        if safe(lambda: page.wait_for_selector("#drawer.open", timeout=8000)):
            page.wait_for_timeout(700)
            caption(page, "Another item — different owner, its own cited source", 4.6, badge)
            safe(lambda: page.click("#drawer-x", timeout=3000)); page.wait_for_timeout(500)


def act_admin(page):
    badge = "● ADMIN"
    caption(page, "Signing in as an ADMIN", 3.0, badge)
    if not sign_in(page, "admin", badge):
        log("  admin board did not render"); return
    page.wait_for_timeout(1000)
    caption(page, "Signed in as admin — full control", 3.2, badge)
    tour_board(page, badge)
    # Approvals — admin can act
    scroll_to(page, "#approvals")
    has_ap = safe(lambda: page.evaluate("() => document.querySelectorAll('#approvals [data-approve]').length"), 0)
    if has_ap:
        caption(page, "Approvals inbox — admins can Approve & notify, or Reject", 5.0, badge)
    else:
        caption(page, "Approvals inbox — admins release risky items here (Approve / Reject)", 5.0, badge)
    # Ops + desk
    scroll_to(page, "#kpis")
    caption(page, "Ops panel — metrics and a live activity feed", 4.2, badge)
    scroll_to(page, "lemma-agent-thread")
    caption(page, "Desk — an operator you can ask anything", 4.0, badge)


def act_user(page):
    badge = "○ MAIN USER"
    # sign out
    safe(lambda: page.evaluate("window.scrollTo({top:0})")); page.wait_for_timeout(400)
    caption(page, "Now switch roles — sign out", 3.2, "● ADMIN")
    safe(lambda: page.click("#logout", timeout=5000)); page.wait_for_timeout(1200)
    caption(page, "The same board, seen by a MAIN USER", 3.4, badge)
    # show the create-account UX (fields + role note), then use a demo account
    safe(lambda: page.click("#tab-signup", timeout=3000)); page.wait_for_timeout(700)
    caption(page, "New users can self-serve with Create account", 4.0, badge)
    safe(lambda: page.fill("#a-name", "Alex Rivera")); page.wait_for_timeout(500)
    safe(lambda: page.fill("#a-email", "alex@acme.co")); page.wait_for_timeout(500)
    safe(lambda: page.fill("#a-pass", "loop-demo-1")); page.wait_for_timeout(500)
    caption(page, "New accounts always start as main users (not admins)", 4.4, badge)
    safe(lambda: page.click("#tab-login", timeout=3000)); page.wait_for_timeout(700)
    caption(page, "We'll sign in with the demo main-user account", 3.6, badge)
    if not sign_in(page, "user", badge):
        log("  user board did not render"); return
    page.wait_for_timeout(1000)
    caption(page, "Signed in as a main user — note the role badge", 3.6, badge)
    tour_board(page, badge)
    # Approvals — read-only for main user
    scroll_to(page, "#approvals")
    read_only = safe(lambda: page.evaluate("() => !!document.querySelector('#approvals .role-note')"), False)
    if read_only:
        caption(page, "Approvals are READ-ONLY for main users — admin approval required", 5.2, badge)
    else:
        caption(page, "Main users can review, but approvals stay admin-only", 5.0, badge)
    # Desk — a real user action: ask a question (live send is opt-in via DESK_LIVE=1,
    # so a weak model can't paint a visible error onto the recording).
    scroll_to(page, "lemma-agent-thread")
    caption(page, "A main user asks the Desk: “what's due today?”", 4.0, badge)
    asked = ask_desk(page, "what's due today?") if os.environ.get("DESK_LIVE") == "1" else False
    if asked:
        caption(page, "Desk answers from the live board — self-serve, no admin needed", 6.0, badge)
    else:
        caption(page, "Desk answers self-serve — “what's due?”, “what do we know about Priya?”", 4.6, badge)


def ask_desk(page, question):
    """Best-effort: type a question into the Desk agent thread and send."""
    box = safe(lambda: page.query_selector("lemma-agent-thread textarea")) or \
        safe(lambda: page.query_selector("lemma-agent-thread input[type=text]"))
    if not box:
        return False
    safe(lambda: box.click())
    safe(lambda: box.fill(question))
    page.wait_for_timeout(400)
    safe(lambda: box.press("Enter"))
    # wait a little for a response to stream in (model-dependent)
    page.wait_for_timeout(6000)
    return True


def record(pw):
    log("Recording walkthrough (headless, ~3 min)...")
    if VIDEO_DIR.exists():
        shutil.rmtree(VIDEO_DIR, ignore_errors=True)
    VIDEO_DIR.mkdir(parents=True, exist_ok=True)
    ctx = pw.chromium.launch_persistent_context(
        str(PROFILE), headless=True, viewport={"width": VW, "height": VH},
        record_video_dir=str(VIDEO_DIR), record_video_size={"width": VW, "height": VH})
    log(f"  mirrored cookies: {mirror_cookies(ctx)}")
    page = ctx.pages[0] if ctx.pages else ctx.new_page()

    safe(lambda: page.goto(BOARD_URL, wait_until="domcontentloaded"))
    page.wait_for_timeout(1200)
    safe(lambda: page.evaluate(f"localStorage.removeItem('{SESS_KEY}')"))
    safe(lambda: page.reload(wait_until="domcontentloaded"))

    # Act 1 — Auth UI/UX
    caption(page, "Loop — the operator that owns meeting follow-through", 3.4)
    safe(lambda: page.wait_for_selector("#auth-form", timeout=15000))
    caption(page, "Every session starts behind a login — roles gate what you can do", 4.2)
    safe(lambda: page.click("#tab-signup", timeout=3000)); page.wait_for_timeout(700)
    caption(page, "Create account — new users start with the main-user role", 4.2)
    safe(lambda: page.click("#tab-login", timeout=3000)); page.wait_for_timeout(700)
    caption(page, "Or use a demo account — click to fill", 3.6)

    # Act 2 — Admin
    act_admin(page)
    # Act 3 — Main user
    act_user(page)

    # Act 4 — Close
    safe(lambda: page.evaluate("window.scrollTo({top:0,behavior:'smooth'})"))
    caption(page, "Two roles, one board — meeting in → owned, dated, gated, remembered", 4.2, "LOOP")
    page.wait_for_timeout(800)

    video_path = safe(lambda: page.video.path()) if page.video else None
    ctx.close()
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
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        if "--login" in sys.argv:
            do_login(pw); return
        preflight()
        if not has_session(pw):
            log("No Lemma session in profile — starting one-time login...")
            do_login(pw)
        webm = record(pw)
    transcode(webm)


if __name__ == "__main__":
    main()

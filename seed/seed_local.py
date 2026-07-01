#!/usr/bin/env python3
"""Cross-platform seeder for the Loop pod (Windows-friendly companion to seed.sh).

Drives the `lemma` CLI via subprocess with json.dumps'd payloads, so there is no
shell-escaping to get wrong. Run AFTER `lemma pods import ./loop`.

Usage (PowerShell / bash), with the local server selected and authenticated:
    python seed/seed_local.py
Optionally pin org/pod explicitly:
    LEMMA_ORG_ID=... LEMMA_POD_ID=... python seed/seed_local.py
"""
from __future__ import annotations

import datetime as dt
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

LEMMA = shutil.which("lemma") or str(Path.home() / ".local" / "bin" / ("lemma.exe" if os.name == "nt" else "lemma"))


def run(args: list[str], *, capture: bool = False, check: bool = True) -> str:
    cmd = [LEMMA, *args]
    res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if res.returncode != 0 and check:
        sys.stderr.write(f"$ lemma {' '.join(args)}\n{res.stdout or ''}\n{res.stderr or ''}\n")
        raise SystemExit(f"command failed: lemma {' '.join(args[:2])}")
    return (res.stdout or "").strip()


def create(table: str, data: dict) -> str:
    out = run(["--output", "json", "records", "create", table, "--data", json.dumps(data)], capture=True)
    try:
        return str(json.loads(out).get("id", ""))
    except Exception:
        return ""


def upload(local: Path, remote: str) -> None:
    try:
        run(["files", "upload", str(local), remote], check=True)
        print(f"  uploaded {remote}")
    except SystemExit:
        print(f"  ! could not upload {remote} (continuing)")


def write_text_file(remote: str, text: str) -> None:
    """Upload text by staging a temp file (works regardless of `files write` flags)."""
    tmp = HERE / ".seed_tmp"
    tmp.write_text(text, encoding="utf-8")
    try:
        run(["files", "upload", str(tmp), remote], check=True)
        print(f"  wrote {remote}")
    except SystemExit:
        print(f"  ! could not write {remote} (continuing)")
    finally:
        tmp.unlink(missing_ok=True)


def main() -> None:
    today = dt.date.today()
    overdue = today - dt.timedelta(days=2)
    soon = today + dt.timedelta(days=1)
    later = today + dt.timedelta(days=6)

    me = ""
    try:
        prof = json.loads(run(["--output", "json", "auth", "status"], capture=True, check=False) or "{}")
        me = str((prof.get("user") or {}).get("id") or prof.get("id") or prof.get("user_id") or "")
    except Exception:
        me = ""
    print(f"owner id for demo items: {me or '<none>'}")

    print("1. knowledge + transcript files")
    upload(HERE / "team-context.md", "/knowledge/team-context.md")
    upload(HERE / "transcripts" / "standup-1.txt", "/transcripts/standup-1.txt")

    print("2. meeting")
    meeting = create("meetings", {
        "title": "Weekly Standup — Monday",
        "source": "upload",
        "transcript_path": "/transcripts/standup-1.txt",
        "status": "ready",
        "organizer_user_id": me or None,
        "summary": ("Acme deck (Priya, high-risk public promise), pipeline schema decision (Marco), "
                    "Vinci vendor pricing needs approval (Dana), rate-limit endpoint (Marco), "
                    "recurring icon set (Priya)."),
    })
    print(f"   meeting={meeting}")

    print("3. twice-recommitted commitment")
    commit = create("commitments", {
        "title": "Deliver the icon set",
        "owner_user_id": me or None,
        "first_seen_meeting_id": meeting,
        "times_recommitted": 2,
        "current_status": "open",
    })
    print(f"   commitment={commit}")

    print("4. action items across every status")
    items = [
        {"meeting_id": meeting, "title": "Ship rate-limit endpoint", "kind": "task", "owner_user_id": me or None,
         "owner_hint": "Marco", "due_date": str(overdue), "status": "confirmed", "risk": "medium", "confidence": 0.9,
         "source_quote": "I'll add the rate-limit endpoint by next Wednesday.", "source_page": 2, "nudge_count": 1},
        {"meeting_id": meeting, "title": "Email Vinci vendor to confirm renewal pricing", "kind": "follow_up",
         "owner_hint": "Dana", "due_date": str(soon), "status": "proposed", "risk": "high", "confidence": 0.55,
         "source_quote": "I need to email the Vinci vendor to confirm the renewal pricing before month end.",
         "source_page": 1},
        {"meeting_id": meeting, "title": "Deliver the customer deck", "kind": "task", "owner_hint": "Priya",
         "due_date": str(later), "status": "confirmed", "risk": "high", "confidence": 0.8,
         "source_quote": "I'll have the new design deck done by Friday.", "source_page": 1, "commitment_id": commit},
        {"meeting_id": meeting, "title": "Standardize on new ingestion schema", "kind": "decision",
         "owner_hint": "Marco", "status": "in_progress", "risk": "low", "confidence": 0.95,
         "source_quote": "we're standardizing on the new ingestion schema, dropping the legacy one.", "source_page": 1},
        {"meeting_id": meeting, "title": "Acme status update call", "kind": "follow_up", "owner_hint": "Dana",
         "due_date": str(soon), "status": "blocked", "risk": "high", "confidence": 0.7,
         "source_quote": "we promised the Acme customer a status update call this Thursday.", "source_page": 2},
        {"meeting_id": meeting, "title": "Publish standup notes", "kind": "task", "owner_hint": "Sam",
         "status": "done", "risk": "low", "confidence": 1.0, "source_quote": "Wrapping up.", "source_page": 2},
    ]
    for it in items:
        create("action_items", {k: v for k, v in it.items() if v is not None})
    print(f"   created {len(items)} action items")

    print("5. memory (structured rows + semantic files)")
    for row in [
        {"subject": "Priya", "kind": "pattern", "statement": "Priya owns design; slipped the deck deadline twice.",
         "confidence": 0.85, "source_meeting_id": meeting},
        {"subject": "Priya", "kind": "person_fact",
         "statement": "Priya is the design lead and owns the customer-facing deck.",
         "confidence": 0.9, "source_meeting_id": meeting},
        {"subject": "Dana", "kind": "norm",
         "statement": "External vendor/customer financial commitments require Sam's approval before sending.",
         "confidence": 0.9, "source_meeting_id": meeting},
    ]:
        create("memory", row)
    write_text_file("/memory/priya.md",
                    "# Memory: Priya\n"
                    "- (person_fact) Priya is the design lead and owns the customer-facing deck.\n"
                    "- (pattern) Priya owns design; slipped the deck deadline twice.\n")
    write_text_file("/memory/dana.md",
                    "# Memory: Dana\n"
                    "- (norm) External vendor/customer financial commitments require Sam's approval before sending.\n")

    print("6. ops metrics (for the Ops panel KPIs)")
    for name, value in [("items_extracted", 6), ("nudges_sent", 1), ("policy_blocks", 1), ("memory_facts_written", 3)]:
        create("metrics", {"name": name, "value": value})

    print("7. activity log (recent feed)")
    for kind, note in [
        ("extracted", "6 action items extracted from Weekly Standup — Monday; 2 high-risk"),
        ("nudged", "Nudged Marco about the overdue rate-limit endpoint"),
        ("redacted", "Redacted sensitive details from a pending external Vinci email"),
        ("confirmed", "Organizer confirmed the customer deck item"),
    ]:
        create("activity_log", {"kind": kind, "note": note, "actor": "operator"})

    print("8. slack mapping placeholder (edit slack_user_id to your real Slack member id)")
    create("user_prefs", {"channel": "slack", "slack_user_id": "U_REPLACE_ME"})

    print("\nDONE. Open the board:  lemma apps open execution-board")


if __name__ == "__main__":
    main()

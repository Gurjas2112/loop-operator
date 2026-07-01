#!/usr/bin/env bash
# Loop — seed the pod so it demos itself.
# Run AFTER `lemma pods import ./loop` and after the pod is selected (lemma pods list).
# Windows: run in Git Bash or WSL. Requires `lemma` + `python` on PATH.
# Not part of `lemma pods import` — file bytes and records don't round-trip through bundles.
set -euo pipefail
cd "$(dirname "$0")"

j() { python -c 'import sys,json; print(json.load(sys.stdin).get(sys.argv[1],""))' "$1"; }

echo "== dates =="
TODAY=$(python -c 'import datetime;print(datetime.date.today())')
OVERDUE=$(python -c 'import datetime;print(datetime.date.today()-datetime.timedelta(days=2))')
SOON=$(python -c 'import datetime;print(datetime.date.today()+datetime.timedelta(days=1))')
LATER=$(python -c 'import datetime;print(datetime.date.today()+datetime.timedelta(days=6))')

echo "== current user id (owner for demo items; may be blank) =="
ME=$(lemma --output json auth status 2>/dev/null | python -c 'import sys,json
try:
  d=json.load(sys.stdin); u=d.get("user") or {}
  print(u.get("id") or d.get("user_id") or "")
except Exception:
  print("")' || true)
echo "ME=${ME:-<unknown>}"

echo "== 1. knowledge: team-context.md -> /knowledge =="
lemma files upload ./team-context.md /knowledge/team-context.md || \
  lemma files write /knowledge/team-context.md --file ./team-context.md

echo "== 2. transcript standup-1 -> /transcripts (pre-processed meeting) =="
lemma files upload ./transcripts/standup-1.txt /transcripts/standup-1.txt || \
  lemma files write /transcripts/standup-1.txt --file ./transcripts/standup-1.txt

MEETING=$(lemma --output json records create meetings --data "{
  \"title\":\"Weekly Standup — Monday\",
  \"source\":\"upload\",
  \"transcript_path\":\"/transcripts/standup-1.txt\",
  \"status\":\"ready\",
  \"organizer_user_id\":${ME:+\"$ME\"}${ME:-null},
  \"summary\":\"Acme deck (Priya, high-risk public promise), pipeline schema decision (Marco), Vinci vendor pricing needs approval (Dana), rate-limit endpoint (Marco), recurring icon set (Priya).\"
}" | j id)
echo "MEETING=$MEETING"

echo "== 3. a twice-recommitted commitment (Priya's icon set) =="
COMMIT=$(lemma --output json records create commitments --data "{
  \"title\":\"Deliver the icon set\",
  \"owner_user_id\":${ME:+\"$ME\"}${ME:-null},
  \"first_seen_meeting_id\":\"$MEETING\",
  \"times_recommitted\":2,
  \"current_status\":\"open\"
}" | j id)
echo "COMMIT=$COMMIT"

owner() { if [ -n "${ME:-}" ]; then echo "\"$ME\""; else echo null; fi; }

echo "== 4. action items across every status (incl. one overdue + one high-risk awaiting approval) =="
# OVERDUE, confirmed, owned -> glows red on the board and is nudgeable by the operator.
lemma records create action_items --data "{\"meeting_id\":\"$MEETING\",\"title\":\"Ship rate-limit endpoint\",\"kind\":\"task\",\"owner_user_id\":$(owner),\"owner_hint\":\"Marco\",\"due_date\":\"$OVERDUE\",\"status\":\"confirmed\",\"risk\":\"medium\",\"confidence\":0.9,\"source_quote\":\"I'll add the rate-limit endpoint by next Wednesday.\",\"source_page\":2,\"nudge_count\":1}"
# HIGH-RISK, proposed -> sits in the approvals path (also unconfirmed).
lemma records create action_items --data "{\"meeting_id\":\"$MEETING\",\"title\":\"Email Vinci vendor to confirm renewal pricing\",\"kind\":\"follow_up\",\"owner_hint\":\"Dana\",\"due_date\":\"$SOON\",\"status\":\"proposed\",\"risk\":\"high\",\"confidence\":0.55,\"source_quote\":\"I need to email the Vinci vendor to confirm the renewal pricing before month end.\",\"source_page\":1}"
# CONFIRMED future
lemma records create action_items --data "{\"meeting_id\":\"$MEETING\",\"title\":\"Deliver the customer deck\",\"kind\":\"task\",\"owner_hint\":\"Priya\",\"due_date\":\"$LATER\",\"status\":\"confirmed\",\"risk\":\"high\",\"confidence\":0.8,\"source_quote\":\"I'll have the new design deck done by Friday.\",\"source_page\":1,\"commitment_id\":\"$COMMIT\"}"
# IN PROGRESS
lemma records create action_items --data "{\"meeting_id\":\"$MEETING\",\"title\":\"Standardize on new ingestion schema\",\"kind\":\"decision\",\"owner_hint\":\"Marco\",\"status\":\"in_progress\",\"risk\":\"low\",\"confidence\":0.95,\"source_quote\":\"we're standardizing on the new ingestion schema, dropping the legacy one.\",\"source_page\":1}"
# BLOCKED
lemma records create action_items --data "{\"meeting_id\":\"$MEETING\",\"title\":\"Acme status update call\",\"kind\":\"follow_up\",\"owner_hint\":\"Dana\",\"due_date\":\"$SOON\",\"status\":\"blocked\",\"risk\":\"high\",\"confidence\":0.7,\"source_quote\":\"we promised the Acme customer a status update call this Thursday.\",\"source_page\":2}"
# DONE
lemma records create action_items --data "{\"meeting_id\":\"$MEETING\",\"title\":\"Publish standup notes\",\"kind\":\"task\",\"owner_hint\":\"Sam\",\"status\":\"done\",\"risk\":\"low\",\"confidence\":1.0,\"source_quote\":\"Wrapping up.\",\"source_page\":2}"

echo "== 5. memory layer: structured rows + semantic /memory files =="
lemma records create memory --data "{\"subject\":\"Priya\",\"kind\":\"pattern\",\"statement\":\"Priya owns design; slipped the deck deadline twice.\",\"confidence\":0.85,\"source_meeting_id\":\"$MEETING\"}"
lemma records create memory --data "{\"subject\":\"Priya\",\"kind\":\"person_fact\",\"statement\":\"Priya is the design lead and owns the customer-facing deck.\",\"confidence\":0.9,\"source_meeting_id\":\"$MEETING\"}"
lemma records create memory --data "{\"subject\":\"Dana\",\"kind\":\"norm\",\"statement\":\"External vendor/customer financial commitments require Sam's approval before sending.\",\"confidence\":0.9,\"source_meeting_id\":\"$MEETING\"}"

lemma files write /memory/priya.md --content "# Memory: Priya
- (person_fact) Priya is the design lead and owns the customer-facing deck.
- (pattern) Priya owns design; slipped the deck deadline twice.
" || printf '# Memory: Priya\n- (person_fact) Priya is the design lead and owns the customer-facing deck.\n- (pattern) Priya owns design; slipped the deck deadline twice.\n' | lemma files write /memory/priya.md --stdin

lemma files write /memory/dana.md --content "# Memory: Dana
- (norm) External vendor/customer financial commitments require Sam's approval before sending.
" || true

echo "== 6. your Slack mapping (EDIT the slack_user_id to your real Slack member id) =="
lemma records create user_prefs --data "{\"channel\":\"slack\",\"slack_user_id\":\"U_REPLACE_ME\"}"

echo "== DONE. standup-2.txt is intentionally NOT processed — run it live in the demo:"
echo "   lemma functions run ingest_transcript --data \"{\\\"title\\\":\\\"Weekly Standup — Following Monday\\\",\\\"transcript_text\\\":\\\"\$(python -c 'print(open(\"./transcripts/standup-2.txt\").read())')\\\"}\""
echo "Open the board:  lemma apps open execution-board"

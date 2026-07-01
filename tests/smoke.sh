#!/usr/bin/env bash
# Loop — bottom-up smoke test. Run after import + seed. Windows: Git Bash / WSL.
# Each block is a gate; stop and fix on the first red.
set -uo pipefail
cd "$(dirname "$0")/.."
pass(){ echo "PASS: $1"; }; fail(){ echo "FAIL: $1"; }

echo "== Gate 1: tables (expect 8) =="
lemma tables list || fail "tables list"
lemma query run "select count(*) from action_items" && pass "action_items queryable"

echo "== Gate: pure-helper unit tests =="
pytest -q tests/test_functions.py && pass "unit tests" || fail "unit tests"

echo "== Gate 3: functions =="
lemma functions run policy_gate --file loop/payloads/policy_gate_block.json && pass "policy_gate (expect allowed:false + redacted number)"
lemma functions run memory_write --file loop/payloads/memory_write_sample.json && pass "memory_write (expect a memory row + /memory/priya.md)"
# persist_items needs a real meeting id — edit loop/payloads/persist_sample.json first, then:
# lemma functions run persist_items --file loop/payloads/persist_sample.json

echo "== Gate: files indexed =="
lemma files stat /knowledge/team-context.md && pass "team-context uploaded"
lemma files search "who owns the deck" --scope /knowledge && pass "knowledge searchable"
lemma files search "slips deck deadlines" --scope /memory && pass "memory searchable"

echo "== Gate 2/4: agents (read the FINAL message) =="
lemma agents chat desk "what do we know about Priya" && pass "desk recalls memory"
lemma agents chat operator "run the daily chase" && pass "operator chase (posts a Slack nudge for the seeded overdue item)"

echo "== Gate 5: workflow (insert a meeting -> run pauses at FORM for high-risk) =="
lemma workflows runs list meeting-intake || fail "workflow runs list"

echo "== Gate 6/7: surface + app =="
lemma surfaces get slack || echo "(surface not yet configured — see scripts/setup-slack.md)"
lemma apps get execution-board && pass "app deployed"

echo "== SMOKE COMPLETE — review any FAIL lines above. =="

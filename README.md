# Loop — AI Meeting-to-Execution Operator

**Loop owns meeting follow-through.** Drop a transcript and Loop turns it into owned, dated,
risk-scored action items; nudges owners on Slack; gates risky external sends behind a human
approval; chases overdue work on its own; and **remembers commitments and context across
meetings** so it gets smarter every week. It is *not* a note-taker — it's the operator that makes
sure what was decided actually happens.

Built entirely on the [Lemma platform](https://github.com/lemma-work/lemma-platform): Postgres-backed
tables, files-as-RAG, one rich agent, functions for multi-write, a workflow with a real human form,
event + cron schedules, a Slack surface, and a live `watchChanges` app — one substrate, no external
vector DB, no fragile hosting.

## The reframe
Meetings end with decisions, tasks, and promises that quietly decay. The built-in "summarize the
meeting" template stops at notes. Loop starts *after* the notes: **ownership, deadlines, risk,
approval, chase, memory.** The user is the **organizer** (who needs follow-through) and the
**owners** (who get specific, gated nudges).

## Architecture
```
ingest_transcript ─▶ meetings (INSERT) ─▶ [schedule] ─▶ meeting-intake workflow
   extractor (recall memory + read transcript, output_schema)
      └▶ persist_items (rows + commitments + metrics)
           └▶ DECISION needs_confirmation? ─┬─ yes ─▶ FORM (organizer approves)
                                            └─ no  ─▶ notify_owners (policy_gate + Slack)
action_items (INSERT) ─▶ reconciler   ·   meetings (UPDATE→ready) ─▶ librarian ─▶ memory_write
CRON 9am ─▶ operator (nudge/escalate)   ·   Slack ─▶ desk ─▶ record_reply
Execution Board app ◀── watchChanges (live) ── tables
```

## Setup

### 0. Prerequisites
```bash
# A container runtime (Docker Desktop or Podman) must be running.
curl -fsSL https://raw.githubusercontent.com/lemma-work/lemma-platform/main/install.sh | bash
uv tool install lemma-terminal
lemma servers select local && lemma auth login && lemma auth status   # expect: authenticated
uv pip install presidio-analyzer presidio-anonymizer structlog pydantic pytest   # for local tests
# Optional but recommended — run the agents on a local open model (zero-cost, private):
#   install Ollama (https://ollama.com), then: ollama pull qwen2.5:7b-instruct
```
Frontend at http://127-0-0-1.sslip.io:3711 (localhost:3711 also works).

### 1. Create the pod + import the bundle
```bash
lemma pods create loop --org "$(lemma orgs list --output json | python -c 'import sys,json;print(json.load(sys.stdin)[0]["id"])')"
lemma pods list                        # select loop
lemma pods import ./loop --dry-run && lemma pods import ./loop
```

### 2. Pin a model runtime, then re-import agents
Loop runs on a **local open-source model by default** — its agents only need structured-JSON output
and tool-calling, which local instruct models (e.g. `qwen2.5:*-instruct`) handle well, at zero cost
and with no data leaving the machine. With [Ollama](https://ollama.com) running:
```bash
pip install lemma-sdk
python scripts/register-open-model.py     # registers an OpenAI-compatible profile + pins all 5 agents
lemma pods import ./loop                   # re-import so agents pick up the runtime
```
Details, model sizing, and the hosted **GPT-5.5** alternative: [scripts/setup-open-model.md](scripts/setup-open-model.md)
and [loop/README.md](loop/README.md) → "Non-bundled setup".

### 3. Slack (not bundled)
Follow [scripts/setup-slack.md](scripts/setup-slack.md): Socket-Mode app → `workspace-slack`
connector account → set `account_id` in [loop/surfaces/slack/slack.json](loop/surfaces/slack/slack.json)
→ `lemma pods import ./loop/surfaces/slack` → `lemma surfaces setup slack`.

### 4. Seed so it demos itself
```bash
bash seed/seed.sh          # Git Bash / WSL on Windows
# or on Windows (PowerShell):
python seed/seed_local.py
lemma apps deploy execution-board ./loop/apps/execution-board/html.html
lemma apps open execution-board
```

**Windows one-shot** (Docker + stack + import + seed):
```powershell
.\scripts\setup-local.ps1 -OpenBoard
```

### 5. Sign in to the Execution Board
The app opens on a **login / signup** screen with click-to-fill demo credentials. Sign in as the
**admin** to approve extracted items, or the **main user** to see the read-only queue.

| Role      | Email             | Password     | Can do                                             |
| --------- | ----------------- | ------------ | -------------------------------------------------- |
| Admin     | `admin@loop.demo` | `loop-admin` | Everything + **Approve / Reject** in Approvals     |
| Main user | `user@loop.demo`  | `loop-user`  | Full board, provenance, Desk; approvals read-only  |

**Create account** registers a new standard (main-user) account. This app-level role gate governs
elevated actions only; the Lemma platform (SuperTokens) remains the real data-access boundary.

### 6. Public live link (share with reviewers)

Expose the local stack on a **public HTTPS URL** via Cloudflare quick tunnel (`cloudflared`):

```powershell
.\scripts\host-live.ps1 -OpenBrowser
```

This writes `.live-url.txt` (Execution Board) and `.live-auth-url.txt` (Lemma sign-in). Share both:
reviewers sign in to Lemma once, then open the board and use the demo credentials above.

Details: [scripts/host-live.md](scripts/host-live.md)

## Submission

- **Live Product Link:** the Cloudflare quick tunnel to the local Execution Board (self-hosted; the
  URL is **ephemeral** and regenerated by `scripts/host-live.ps1` — the current value is in
  `scripts/LIVE_URL.md` / `.live-url.txt`). Reviewers open the **Lemma sign-in** link once, then the
  board link, and use the demo credentials above.
- **Demo video:** [`essential_docs/loop-demo.mp4`](essential_docs/loop-demo.mp4) — a recorded
  walkthrough of the live board (sign-in → situation room → Deadline Horizon → swimlanes → approvals
  → provenance drawer with remembered facts → ops panel → desk).
- **Architecture reference:** [`essential_docs/system-architecture.md`](essential_docs/system-architecture.md)
  and [`essential_docs/system-architecture.pdf`](essential_docs/system-architecture.pdf) — component/
  deployment, ER, workflow, sequence, state-machine, and memory data-flow UML diagrams.

Regenerate the submission artifacts:

```bash
python scripts/build-architecture-pdf.py   # essential_docs/system-architecture.pdf
python scripts/record-demo.py              # essential_docs/loop-demo.mp4 (verifies the stack first)
```

## Smoke test
```bash
pytest tests/test_functions.py     # pure-helper unit tests (offline)
bash tests/smoke.sh                # bottom-up gates: tables → files → functions → agents → workflow → app
```

## The 60-second demo (hero run)
1. Drop `standup-2.txt`:
   `lemma functions run ingest_transcript --data "{\"title\":\"Standup — Following Monday\",\"transcript_text\":\"$(cat seed/transcripts/standup-2.txt)\"}"`.
2. Within ~90s the board fills with owned, dated items; your phone buzzes on Slack with the risky
   **Vinci contract / Acme quote** to approve.
3. **Approve** in Slack (or the app's Approvals inbox) → the owner's nudge sends and the board
   updates **live**.
4. Reply `done` in Slack → the item flips to ✅.
5. Open its **provenance drawer** → verbatim transcript quote + page + **what Loop remembers** about
   the owner (Priya slips deck deadlines).

## Where each concern lives
- **Database (system of record):** Postgres, via typed Lemma tables with RLS. No second DB.
- **Memory (3 native tiers, the pod *is* the RAG system):** `/memory` files (semantic, auto-indexed) +
  `memory` table (structured, superseding) + Lemma `conversations` (working). `librarian` distils →
  `memory_write` → next meeting `extractor`/`operator`/`desk` recall.
- **Guardrails:** `output_schema` (typed extraction), zero-default name-based grants, `policy_gate`
  (Presidio PII redaction + high-risk-unless-confirmed block), the approval **FORM**, operator
  `request_approval` before escalation.
- **Caching:** `extraction_cache` keyed by SHA-256 of the transcript.
- **Observability:** `structlog` JSON logs, a `metrics` table, an `activity_log` audit trail, the
  app's **Ops panel**, and `lemma workflows runs` history.

## Honest limitations
- **Owner resolution** depends on `/knowledge/team-context.md` + memory; ambiguous names are left
  unowned (which routes them through the approval FORM) rather than guessed.
- **Extraction is imperfect** — that's exactly why the confirm FORM + provenance drawer exist; a
  human confirms owners/dates, and every item cites its source quote + page.
- **`user_prefs` is RLS-scoped**, so cross-owner Slack resolution in a workload sees the invoking
  user's mapping; the demo maps one user. Multi-user Slack routing is a documented next step.
- **Reconciliation is heuristic** (fuzzy title match + recommitment count) and advisory/editable.
- **Slack op id + model runtime** are environment-specific — confirm via
  `lemma connectors operations search` and `lemma runtime profiles` (see the runbooks). Smaller local
  models trade some extraction precision for cost/privacy; step up model size if schema output slips.
- **App login is a demo role gate**, not production auth: accounts + salted-SHA-256 hashes live in the
  browser's `localStorage` and only decide which actions a seat may take. The platform's own session
  (SuperTokens) is the real identity/data-access boundary.
- Diarized transcript in → best out; garbled ASR degrades extraction quality.

## Repo map
- [`loop/`](loop/) — the pod bundle (imported as one unit). Runbook: [loop/README.md](loop/README.md).
- [`essential_docs/`](essential_docs/) — submission reference: `system-architecture.md` + `.pdf`
  (UML diagrams) and `loop-demo.mp4` (recorded walkthrough).
- [`seed/`](seed/) — `seed.sh`, `team-context.md`, two standup transcripts.
- [`tests/`](tests/) — `test_functions.py` (pytest), `smoke.sh`.
- [`scripts/setup-slack.md`](scripts/setup-slack.md) — Slack connector setup.
- [`scripts/setup-open-model.md`](scripts/setup-open-model.md) + [`scripts/register-open-model.py`](scripts/register-open-model.py) — run agents on a local open model.
- [`scripts/setup-local.ps1`](scripts/setup-local.ps1) — Windows one-shot: Docker + stack + import + seed.
- [`scripts/host-live.ps1`](scripts/host-live.ps1) + [`scripts/host-live.md`](scripts/host-live.md) — public HTTPS tunnel for demos.
- `BUILD.md` — the full build runbook this repo implements.

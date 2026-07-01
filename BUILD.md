# BUILD.md — Loop: AI Meeting-to-Execution Operator (Lemma SDK)

**Read this whole file once, then execute Phases 0→9 in order. Do not skip a phase's gate.**

Loop is the operator that **owns meeting follow-through**. Transcript in → owned, dated, risk-scored
action items → owners nudged on Slack → risky items gated behind a human approval → overdue work
chased autonomously → commitments and context **remembered across meetings**.

- **Platform docs:** https://lemma.work/docs · **Platform repo:** https://github.com/lemma-work/lemma-platform

> This repo is the *implementation* of the runbook. The authoritative platform reference used while
> building is the `lemma-builder` skill in the platform repo (bundle format, permission ids, grant
> model, function headers, `Pod.from_env()` shapes, workflow/schedule/surface/app JSON). Corrections
> applied vs the original spec are documented in [loop/README.md](loop/README.md) and this file's notes.

## The single stack
- **Runtime / host:** Lemma local stack (`lemma-stack`, Docker) at `127-0-0-1.sslip.io:3711` (API `:8711`).
- **CLI / packaging:** `lemma-terminal` via `uv`.
- **Agent LLM:** OpenAI GPT-5.5 via an OpenAI-compatible runtime profile (`OPENAI_API_KEY`).
- **Database:** PostgreSQL, exposed as Lemma tables (typed columns, RLS, SQL via `pod.query`).
- **Memory layer:** native 3-tier — `/memory` files (semantic, auto-indexed) + `memory` table
  (structured/entity) + Lemma `conversations` (working).
- **Chat surface:** Slack (Socket Mode custom app).
- **App UI:** single-file HTML (Tailwind CDN + live `datastore.watchChanges`).
- **Caching:** content-addressed `extraction_cache` table (SHA-256 of transcript → extractor JSON).
- **Guardrails:** `policy_gate` function (Presidio PII redaction + action policy) + approval FORM +
  `output_schema` + zero-default grants.
- **Observability:** `structlog` JSON logs + `metrics` + `activity_log` tables + in-app Ops panel +
  `lemma-stack logs`.
- **VCS:** GitHub.

## Bundle rules (memorized)
- Folder name **must equal** the resource `name`; bundle JSON is JSONC (comments + trailing commas OK).
- Long code/text lives in sidecars via `{"$file":"code.py"}` / `{"$file":"instruction.md"}`.
- **Function schemas are derived from `code.py` headers — never declared in JSON**; every function JSON
  carries `"type":"API"`.
- Grants are **name-based and replaced on every import**; import order is
  tables→files→functions→agents→workflows→schedules→surfaces→app.
- Connectors/accounts/file-bytes are **not** bundled — seed them.
- `DATASTORE_EVENT` gives the changed row id at **`start.metadata.record_id`** (never `start.payload.id`).
- **Function-as-tool** requires three grants on the parent agent: `function.read` + `function.execute`
  **plus** the function's own resource grants mirrored onto the parent.
- **`agent_runtime`** is an object `{profile_id, model_name}` (not a bare string).

---

## PHASE 0 — Prerequisites & install
```bash
# A container runtime (Docker Desktop OR Podman) must be running.
curl -fsSL https://raw.githubusercontent.com/lemma-work/lemma-platform/main/install.sh | bash
uv tool install lemma-terminal
lemma servers select local
lemma auth login
lemma auth status            # expect: authenticated
uv pip install presidio-analyzer presidio-anonymizer structlog pydantic pytest
```
**Gate 0:** `lemma auth status` = authenticated; frontend loads at http://127-0-0-1.sslip.io:3711.

## PHASE 1 — Pod, tables, files
```bash
lemma pods create loop --org "$(lemma orgs list --output json | python -c 'import sys,json;print(json.load(sys.stdin)[0]["id"])')"
lemma pods import ./loop --dry-run && lemma pods import ./loop
```
Tables: `meetings, action_items, commitments, activity_log, extraction_cache, metrics, memory` (shared),
`user_prefs` (RLS). System columns `id/created_at/updated_at/user_id` are auto — never declared.
**Gate 1:** `lemma tables list` shows 8 tables; `lemma query run "select count(*) from action_items"` = 0.

## PHASE 2 — The extractor agent + GPT-5.5 runtime
Create an OpenAI-compatible runtime profile, set `agent_runtime:{profile_id,model_name:"gpt-5.5"}` on
each agent, re-import agents. One rich-output agent: classify + extract + resolve owner + risk +
confidence + cite, single pass.
**Gate 2:** upload a transcript, create a `meetings` row, `lemma agents chat extractor "extract meeting <id>"`
→ final message JSON matches the schema with page numbers.

## PHASE 3 — Functions
`ingest_transcript, persist_items, policy_gate, notify_owners, record_reply, memory_write`.
**Gate 3:** `policy_gate` on a high-risk unconfirmed external send returns `allowed:false` + redacted PII;
`memory_write` writes a `memory` row + `/memory/priya.md`.

## PHASE 4 — Operator, reconciler, librarian, desk agents
All pinned to the `gpt` runtime. Function-as-tool grants are explicit (see bundle rules).
**Gate 4:** `operator` posts a Slack nudge for a seeded overdue item; `librarian` writes ≥1 memory row;
`desk` recalls it.

## PHASE 5 — Intake workflow + schedules
`meeting-intake`: extract → persist → gate(DECISION) → confirm(FORM) → notify. Schedules:
`intake-on-meeting` (DATASTORE), `daily-chase` (CRON 9am), `reconcile-on-item` (DATASTORE),
`curate-memory` (DATASTORE).
**Gate 5:** insert a `meetings` row → a run appears, pauses at the FORM for a high-risk item, then on
`lemma workflows runs submit-form <run> --data '{"approved":true}'` proceeds to notify.

## PHASE 6 — Slack connector + surface
See [scripts/setup-slack.md](scripts/setup-slack.md). **Gate 6:** DM the bot "what's due today" → `desk`
replies with the seeded queue.

## PHASE 7 — The app (single-file HTML, live)
Dark ops "situation room": Deadline Horizon rail, status swimlanes colored by risk, Approvals inbox,
Ops panel, Desk chat, provenance drawer with "What we remember". Live via `watchChanges`.
**Gate 7:** board loads; inserting an `action_items` row appears live; the drawer shows quote + page +
remembered facts.

## PHASE 8 — Seed so it demos itself
`bash seed/seed.sh`. **Gate 8:** open the app cold → full board, one glowing overdue item, one item in
the Approvals inbox, Deadline Horizon populated, remembered facts on the owner's card.

## PHASE 9 — Test, deploy, submit
```bash
pytest tests/test_functions.py
bash tests/smoke.sh
lemma pods import ./loop
lemma apps deploy execution-board ./loop/apps/execution-board/html.html
git add -A && git commit -m "Loop: meeting-to-execution operator on Lemma" && git push
```
Record the 60-second hero run (see [README.md](README.md)).

## If time runs short, cut in THIS order (never below the line)
librarian/memory recall → reconciler → commitments linking → Ops panel polish → Deadline-Horizon animation.
**Never cut:** ingest→extractor→persist→board, the approval FORM, the Slack nudge, provenance.

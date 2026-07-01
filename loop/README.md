# Loop pod — runbook

This is the Lemma pod bundle for **Loop**. Import it as one unit, then do the non-bundled setup
(runtime profile, Slack connector, file bytes, seed records) recorded below.

## Resources
- **Tables (8):** `meetings`, `action_items`, `commitments`, `activity_log`, `extraction_cache`,
  `metrics`, `memory` (all shared), `user_prefs` (RLS-on — the only per-user table).
- **Files:** `/transcripts` (auto-indexed provenance), `/knowledge` (team-context), `/memory`
  (semantic long-term memory).
- **Functions:** `ingest_transcript`, `persist_items`, `policy_gate`, `notify_owners`,
  `record_reply`, `memory_write`.
- **Agents:** `extractor`, `operator`, `reconciler`, `librarian`, `desk`.
- **Workflow:** `meeting-intake` (extract -> persist -> gate -> confirm FORM -> notify).
- **Schedules:** `intake-on-meeting`, `daily-chase`, `reconcile-on-item`, `curate-memory`.
- **Surface:** `slack` (default agent `desk`).
- **App:** `execution-board` (single-file HTML, live via `watchChanges`).

## Import
```bash
lemma pods import ./loop --dry-run    # validate everything first
lemma pods import ./loop              # upsert by name (dependency-ordered)
lemma pods doctor loop                # check grants/targets/surfaces wiring
```

## Non-bundled setup (do after import)
1. **Runtime profile.** Agents need an OpenAI-compatible profile pinned via each
   `agents/*/*.json` `agent_runtime` block. Two supported paths:
   - **Local open-source model (recommended, zero-cost).** Loop's agents only need
     structured-JSON output + tool-calling, which local instruct models handle well.
     With [Ollama](https://ollama.com) running, one command registers the profile and
     pins it on all five agents:
     ```bash
     pip install lemma-sdk
     python ../scripts/register-open-model.py            # default qwen2.5:3b-instruct
     lemma pods import ./loop                             # re-import so agents pick it up
     ```
     Full guide (models, sizing, `host.docker.internal` note): `../scripts/setup-open-model.md`.
   - **Hosted GPT-5.5 (or any provider).** Create an OpenAI-compatible profile pointing at
     the provider, then set `agent_runtime: {"profile_id":"<id>","model_name":"gpt-5.5"}`
     in each `agents/*/*.json` and re-import. (Until a profile is pinned, agents run on the
     system default runtime.)
2. **Slack connector + surface** — see `../scripts/setup-slack.md`. Set `account_id` + a real
   channel in `surfaces/slack/slack.json` before enabling.
3. **File bytes + seed records** — run `../seed/seed.sh` (Git Bash / WSL). It uploads
   `team-context.md`, seeds a full board (incl. one overdue + one high-risk awaiting approval),
   a twice-recommitted commitment, the memory layer, and your `user_prefs` mapping.

## Verify (gates)
- `lemma tables list` -> 8 tables; `lemma query run "select count(*) from action_items"`.
- `lemma functions run policy_gate --file payloads/policy_gate_block.json` -> `allowed:false` + redacted number.
- `lemma agents chat extractor "extract meeting <id>"` -> JSON matching the output schema with page numbers.
- Insert a `meetings` row -> a run appears in `lemma workflows runs list`, pauses at the FORM for the
  high-risk item; `lemma workflows runs submit-form <run> --data '{"approved":true}'` -> proceeds to notify.
- `lemma agents chat desk "what do we know about Priya"` -> recalls seeded memory.

## Notable design decisions vs a naive build
- One rich **extractor** agent (classify+extract+own+risk+cite in a single `output_schema`), not a chain.
- **Function-as-tool grants are explicit**: each parent agent (operator/librarian/desk) holds
  `function.read`+`function.execute` on its tool **and mirrors that function's own resource grants**
  (a hard requirement of the platform).
- `agent_runtime` is an object `{profile_id, model_name}`; left commented so the bundle imports before
  the env-specific profile exists. Loop runs on a **local open-source model by default**
  (`scripts/register-open-model.py`), with hosted GPT-5.5 as a drop-in alternative.
- The **Execution Board app** gates elevated actions (approve/reject extracted items) behind an
  app-level **admin** role via a login/signup screen. Demo credentials — admin `admin@loop.demo` /
  `loop-admin`, main user `user@loop.demo` / `loop-user`. This role gate sits on top of the platform's
  own (SuperTokens) session, which remains the real data-access boundary.

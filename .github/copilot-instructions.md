# Loop — coding-agent instructions

1. This repo is a **Lemma pod bundle**. The full build runbook is `BUILD.md` — read it before changing anything.
2. Bundle rules: folder name **must equal** the resource `name`; JSON is JSONC (comments + trailing commas OK).
3. Long code/text lives in sidecars: `{"$file":"code.py"}` / `{"$file":"instruction.md"}`.
4. Function schemas are **derived from `code.py` headers** — never declared in JSON. Every function JSON needs `"type":"API"`.
5. Grants are **name-based and replaced on every import**. Zero access by default — grant every table/folder/connector explicitly.
6. Function-as-tool = three grants on the parent agent: `function.read` + `function.execute` **plus** the function's own resource grants mirrored onto the parent.
7. Agents pin the runtime via `"agent_runtime": {"profile_id": "<id>"}` (OpenAI-compatible GPT profile).
8. `DATASTORE_EVENT` exposes the changed row id at `start.metadata.record_id` — never `start.payload.id`.
9. Guardrails are non-negotiable: `output_schema`, `policy_gate` (Presidio + high-risk block), the approval FORM, zero-default grants.
10. Import order is tables -> files -> functions -> agents -> workflows -> schedules -> surfaces -> app; connectors/file-bytes/seed are set up by CLI, not bundled.

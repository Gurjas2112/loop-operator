# Loop — System Architecture & Workflow

**Loop is the operator that owns meeting follow-through.** A transcript goes in; owned, dated,
risk-scored action items come out — owners are nudged on Slack, risky items are gated behind a human
approval, overdue work is chased autonomously, and commitments + context are **remembered across
meetings**. It is *not* a note-taker; it is the operator that makes sure what was decided actually
happens.

This document is the reference architecture for the submission: it maps every moving part and the
UML diagrams that describe them (component/deployment, entity-relationship, workflow activity,
end-to-end sequence, state machine, and the memory data-flow).

- **Platform:** [Lemma](https://github.com/lemma-work/lemma-platform) local stack (Docker).
- **Agent runtime:** local **Ollama** open model `qwen2.5:3b-instruct` (tools-capable), reached from
  the agent sandbox at `host.docker.internal:11434/v1` via an OpenAI-compatible runtime profile —
  zero API cost, nothing leaves the machine. Hosted GPT-5.5 is a drop-in alternative.
- **One substrate:** Postgres-backed tables, files-as-RAG, one rich agent, functions for multi-write,
  a workflow with a real human FORM, event + cron schedules, a Slack surface, and a live
  `watchChanges` app. No external vector DB, no second database.

---

## 1. Deployment / Component diagram

How the running system is wired — from the reviewer's browser, through the public Cloudflare tunnels,
into the Dockerized Lemma stack, out to the local model and Slack.

```mermaid
flowchart TB
    subgraph Client["Reviewer / Organizer"]
        Browser["Web browser<br/>(Execution Board + Lemma sign-in)"]
        SlackApp["Slack app<br/>(Socket Mode)"]
    end

    subgraph Tunnel["Cloudflare quick tunnels (public HTTPS)"]
        T1["board tunnel → :8711"]
        T2["auth tunnel → :3711"]
    end

    subgraph Host["Local host (Docker Desktop)"]
        subgraph Stack["Lemma local stack"]
            FE["lemma-local-frontend<br/>:3711"]
            BE["lemma-local-backend<br/>:8711 (API + app host)"]
            AB["lemma-local-agentbox<br/>(agent/function sandboxes)"]
            PG[("lemma-local-db<br/>PostgreSQL — system of record")]
            RD[("lemma-local-redis<br/>queues / sessions")]
            ST["lemma-local-supertokens<br/>identity"]
        end
        OLL["Ollama<br/>qwen2.5:3b-instruct<br/>:11434/v1"]
    end

    subgraph Pod["Loop pod (bundle)"]
        TBL["8 tables"]
        FN["6 functions"]
        AG["5 agents"]
        WF["meeting-intake workflow"]
        SCH["4 schedules"]
        SURF["Slack surface"]
        APP["execution-board app"]
    end

    Browser --> T1 --> BE
    Browser --> T2 --> FE
    FE <--> BE
    BE <--> PG
    BE <--> RD
    BE <--> ST
    BE <--> AB
    AB -->|OpenAI-compatible| OLL
    BE --- Pod
    AG -.runs in.-> AB
    FN -.runs in.-> AB
    SURF <--> SlackApp
    APP -->|watchChanges live| BE
```

---

## 2. Entity-relationship diagram (Postgres tables)

Every Lemma table is a typed Postgres table with row-level security. `id / created_at / updated_at /
user_id` are system columns (auto). Only `user_prefs` has RLS enabled (per-user); the rest are shared
pod state.

```mermaid
erDiagram
    meetings ||--o{ action_items : "has"
    meetings ||--o{ memory : "sources"
    commitments ||--o{ action_items : "links"
    action_items ||--o{ activity_log : "audited by"
    memory ||--o| memory : "superseded_by"

    meetings {
        UUID id PK
        TEXT title
        DATETIME occurred_at
        ENUM source
        FILE_PATH transcript_path
        TEXT transcript_sha "cache key"
        USER organizer_user_id
        ENUM status "ingested|extracting|ready"
        TEXT summary
        JSON attendees
    }
    action_items {
        UUID id PK
        SERIAL number
        UUID meeting_id FK
        TEXT title
        ENUM kind "task|decision|follow_up|risk"
        USER owner_user_id
        TEXT owner_hint
        DATE due_date
        ENUM status "proposed..done"
        ENUM risk "low|medium|high"
        FLOAT confidence
        TEXT source_quote
        INTEGER source_page
        INTEGER nudge_count
        DATETIME last_nudged_at
        UUID commitment_id FK
    }
    commitments {
        UUID id PK
        TEXT title
        USER owner_user_id
        UUID first_seen_meeting_id
        INTEGER times_recommitted
        ENUM current_status "open|done|dropped"
        BOOLEAN is_reversed
    }
    activity_log {
        UUID id PK
        UUID action_item_id FK
        ENUM kind "extracted|nudged|replied|..."
        TEXT note
        TEXT actor "user id or operator"
    }
    memory {
        UUID id PK
        TEXT subject "person / entity"
        ENUM kind "person_fact|preference|norm|decision|pattern"
        TEXT statement
        FLOAT confidence
        UUID source_meeting_id FK
        DATETIME last_seen_at
        UUID superseded_by FK
    }
    extraction_cache {
        UUID id PK
        TEXT sha "SHA-256 of transcript"
        JSON payload
        TEXT model
    }
    metrics {
        UUID id PK
        TEXT name
        FLOAT value
        JSON labels
    }
    user_prefs {
        UUID id PK
        ENUM channel
        TEXT slack_user_id
        JSON quiet_hours
    }
```

---

## 3. Meeting-intake workflow (activity diagram)

The choreography that runs on every new `meetings` row. `DATASTORE_EVENT` exposes the changed row id
at `start.metadata.record_id`. The **DECISION** gate routes uncertain/risky/unowned batches to a real
human **FORM**; everything else flows straight to notification.

```mermaid
flowchart TD
    Start(["● meetings INSERT<br/>start.metadata.record_id"]) --> Extract

    Extract["AGENT: extractor<br/>recall memory + read transcript<br/>→ items[] (output_schema)"]
    Extract --> Persist["FUNCTION: persist_items<br/>rows + commitments + metrics<br/>→ needs_confirmation, organizer_member_id"]
    Persist --> Gate{"DECISION<br/>needs_confirmation?"}
    Gate -->|"no (default)"| Notify
    Gate -->|yes| Confirm["FORM: organizer approval<br/>assignee = organizer_member_id<br/>{approved: bool, edits: str}"]
    Confirm --> Notify["FUNCTION: notify_owners<br/>policy_gate → Slack DM<br/>nudge_count++, log nudged"]
    Notify --> End(["◉ END"])
```

`needs_confirmation` is set true by `persist_items` when any item is low-confidence (< 0.6), unowned,
or high-risk — so imperfect extraction is caught by a human instead of silently acted on.

---

## 4. End-to-end sequence diagram (the hero flow)

From dropping a transcript to a live board update and a Slack reply — including memory recall and the
approval gate.

```mermaid
sequenceDiagram
    actor Org as Organizer
    participant ING as ingest_transcript
    participant DB as Postgres (tables)
    participant WF as meeting-intake
    participant EX as extractor (Ollama)
    participant MEM as memory (files + table)
    participant PS as persist_items
    participant FORM as Approval FORM
    participant NO as notify_owners
    participant PG as policy_gate
    participant SL as Slack
    participant APP as Execution Board
    actor Own as Owner

    Org->>ING: transcript_text
    ING->>DB: create meetings row (sha, path)
    DB-->>WF: DATASTORE_EVENT (INSERT)
    WF->>EX: extract(meeting_id)
    EX->>MEM: recall people/topics
    EX->>DB: read transcript + meeting
    EX-->>WF: items[] (owned, dated, risk, quote+page)
    WF->>PS: persist(items, summary)
    PS->>DB: action_items + commitments + metrics
    PS-->>WF: needs_confirmation?
    alt risky / unowned / low-confidence
        WF->>FORM: assign to organizer
        Org-->>FORM: approve
    end
    WF->>NO: notify owners
    NO->>PG: policy_gate(text, high-risk?)
    PG-->>NO: allowed + redacted text
    NO->>SL: DM owner the nudge
    NO->>DB: nudge_count++, log nudged
    DB-->>APP: watchChanges → live update
    Own->>SL: "done"
    SL->>DB: record_reply → status = done
    DB-->>APP: watchChanges → item flips ✅
```

A parallel path keeps work honest without a meeting: the **daily-chase** cron wakes the `operator`
(09:00 weekdays) to nudge/escalate due + overdue items, and Slack messages route to the `desk` agent
for Q&A ("what's due today", "what do we know about Priya", "mark #12 done").

---

## 5. Action-item lifecycle (state machine)

Extracted items start `proposed`; the approval FORM (or auto-confirm for safe items) promotes them to
`confirmed`, after which owners drive them to completion.

```mermaid
stateDiagram-v2
    [*] --> proposed: extracted
    proposed --> confirmed: approved / safe (auto)
    proposed --> dropped: rejected
    confirmed --> in_progress: owner starts
    in_progress --> blocked: owner blocked
    blocked --> in_progress: unblocked
    confirmed --> done: reply "done"
    in_progress --> done: reply "done"
    confirmed --> dropped
    in_progress --> dropped
    done --> [*]
    dropped --> [*]
```

---

## 6. Three-tier memory data-flow

The pod *is* the RAG system. The `librarian` distils durable facts after each meeting; the writer
persists them to both a structured table and auto-indexed markdown; later meetings **recall** them.

```mermaid
flowchart LR
    subgraph Sources
        M["meetings (status → ready)"]
        AI["action_items"]
        C["commitments"]
    end
    M -->|UPDATE event| LIB["AGENT: librarian<br/>distil durable facts only"]
    AI --> LIB
    C --> LIB
    LIB --> MW["FUNCTION: memory_write"]

    subgraph Tier1["Tier 1 — Semantic / long-term"]
        FMEM["/memory/*.md<br/>auto-indexed + embedded"]
    end
    subgraph Tier2["Tier 2 — Structured / entity"]
        TMEM[("memory table<br/>facts + confidence + supersession")]
    end
    subgraph Tier3["Tier 3 — Working"]
        CONV["Lemma conversations<br/>per-surface DM state (24h reset)"]
    end

    MW --> FMEM
    MW --> TMEM

    FMEM -.recall.-> EX["extractor"]
    TMEM -.recall.-> EX
    FMEM -.recall.-> OP["operator (nudge slippers earlier)"]
    TMEM -.recall.-> OP
    FMEM -.recall.-> DK["desk (answer 'what do we know about X')"]
    CONV -.thread state.-> DK
```

---

## 7. Event & schedule map

| Schedule | Type | Trigger | Runs |
| --- | --- | --- | --- |
| `intake-on-meeting` | DATASTORE | `meetings` INSERT | `meeting-intake` workflow |
| `daily-chase` | TIME | cron `0 9 * * 1-5` | `operator` agent (nudge / escalate) |
| `reconcile-on-item` | DATASTORE | `action_items` INSERT | `reconciler` agent (contradiction / recommitment) |
| `curate-memory` | DATASTORE | `meetings` UPDATE | `librarian` agent (grow memory) |

---

## 8. Components at a glance

| Layer | Resources |
| --- | --- |
| **Tables (8)** | `meetings`, `action_items`, `commitments`, `activity_log`, `memory`, `metrics`, `extraction_cache`, `user_prefs` (RLS) |
| **Functions (6)** | `ingest_transcript`, `persist_items`, `policy_gate`, `notify_owners`, `record_reply`, `memory_write` |
| **Agents (5)** | `extractor` (one rich judgment pass), `operator` (chaser), `reconciler`, `librarian` (memory curator), `desk` (Slack Q&A) |
| **Workflow (1)** | `meeting-intake` (extract → persist → gate → confirm/notify → end) |
| **Schedules (4)** | `intake-on-meeting`, `daily-chase`, `reconcile-on-item`, `curate-memory` |
| **Surface** | `slack` (Socket Mode, default agent `desk`) |
| **Files (3 folders)** | `/transcripts` (provenance), `/knowledge` (team-context), `/memory` (semantic) |
| **App** | `execution-board` (single-file HTML, live `watchChanges`) |

---

## 9. Guardrails, caching & observability

- **Guardrails:** `output_schema` forces typed, routable extractor output; **zero-default name-based
  grants** (each workload touches only its named resources); `policy_gate` runs **Presidio** PII
  redaction on anything leaving the pod and **blocks external high-risk sends unless
  `status=confirmed`**; the approval **FORM** is the human checkpoint; the operator uses
  `request_approval` before escalating.
- **Caching:** `extraction_cache` keyed by **SHA-256 of the transcript** — re-ingesting the same
  transcript returns stored extractor JSON instead of re-calling the model.
- **Observability:** `structlog` JSON logs in every function (`lemma-stack logs`), a `metrics` table
  (counts, nudges, `memory_facts_written`), an `activity_log` audit trail, the app's **Ops panel**,
  and `lemma workflows runs` history.

---

## 10. Access & live link

- **Live Product Link (submission):** public Cloudflare quick tunnel to the local Execution Board
  (ephemeral — regenerated with `scripts/host-live.ps1`). See the repo `README.md` for the current URL.
- **App demo login (role gate):** `admin@loop.demo` / `loop-admin` (can approve/reject) ·
  `user@loop.demo` / `loop-user` (read-only approvals). This app-level gate governs elevated actions;
  the Lemma platform (SuperTokens) remains the real identity/data-access boundary.
- **Demo video:** [`loop-demo.mp4`](loop-demo.mp4) — the full workflow walkthrough.

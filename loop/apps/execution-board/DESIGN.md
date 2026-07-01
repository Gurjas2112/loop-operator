# Execution Board — DESIGN.md

## Purpose & persona
The **meeting organizer** opens this after (or during) a meeting to see that follow-through is
actually happening. It is not a note viewer and not a generic Kanban — it is an **ops "situation
room" with a deadline horizon**. The subject of the screen is *commitments coming due*.

## The first 30 seconds (the hero)
On cold open the board is already full (seeded), so the organizer immediately sees:
- a big **DUE TODAY** counter (display type),
- a glowing **overdue** item on the board (SLA red, one subtle pulse),
- one item sitting in the **Approvals inbox** waiting for a decision,
- the **Deadline Horizon** rail populated with dots drifting toward the NOW line,
- **remembered facts** on an owner's card ("slipped the deck deadline twice").

No marketing intro, no empty state on open.

## Layout
- **Header** — product mark, live DUE TODAY / OVERDUE / AT-RISK counters, a mono "commitment age"
  clock, connection status.
- **Deadline Horizon** (signature element) — a horizontal rail; each open item is a dot placed by
  `due_date`, drifting toward a vertical **NOW** line and crossing it (turning SLA-red with one pulse)
  when overdue. Color encodes SLA state, never decoration.
- **Left / main** — swimlane board by status (Proposed -> Confirmed -> In-progress -> Blocked ->
  Done), each card colored by risk, with owner, due date, item #, and remembered-fact chips.
- **Right sidebar** —
  - **Approvals inbox**: renders the workflow FORM waits assigned to the user
    (`workflows.runs.waitingAssignedToMe`) with **Approve & notify owner** / **Reject**.
  - **Ops panel**: counters from `metrics` + a recent `activity_log` feed.
  - **Desk**: the `desk` agent via the `<lemma-agent-thread>` web component.
- **Provenance drawer** (row click) — verbatim `source_quote` + transcript page + the item's
  activity timeline + a **"What we remember"** strip (the owner's `memory` rows). Recall is visible
  on the board, not just in chat.

## Data (by name)
- Tables: `action_items` (board), `meetings` (provenance), `activity_log` (timeline + ops),
  `metrics` (ops), `memory` (remembered facts), `commitments` (recommitment flags).
- Workflows: `meeting-intake` (approvals inbox via wait assignments).
- Agents: `desk` (chat).

## Sign-in & roles
A **login / signup gate** fronts the board. It selects the acting role that governs elevated
actions; the platform (SuperTokens) session is still the real data-access boundary underneath.
- **Sign in** with an existing account, or **Create account** (new accounts are standard
  main-users). Passwords are salted-SHA-256 hashed and accounts persist in `localStorage`.
- **Roles.** `admin` sees **Approve & notify owner** / **Reject** in the Approvals inbox and can
  release items; `user` sees the same queue read-only with an "admin approval required" note.
- The header shows the signed-in email, a role badge, and **Sign out**.
- **Demo credentials** (shown on the card, click-to-fill): admin `admin@loop.demo` / `loop-admin`,
  main user `user@loop.demo` / `loop-user`.

> This is a front-of-app **role** gate for the demo, not production auth — real identity/session
> security is the Lemma platform's job; this layer only decides which actions the seat may take.

## Live, never poll
Subscribe with `datastore.watchChanges({ onChange })`; a change debounces a refresh so new/updated
rows animate in. Respect `prefers-reduced-motion`; visible keyboard focus; works at 375px.

## Design tokens
- Palette (dark ops console): base `#0E1116`, panel `#161B22`, hairline `#232A34`, ink `#E7ECF3`,
  muted `#8B97A7`. SLA state: on-track `#3DD9B0`, at-risk `#F5A623`, overdue `#FF5C6C`.
- Type: display **Space Grotesk**, body **Inter**, mono **JetBrains Mono** (ids, timestamps, age ticker).
- Copy: active voice, end-user words ("Approve & notify owner", "Overdue by 2 days"), empty states
  that invite action ("No items yet — drop a transcript to begin").

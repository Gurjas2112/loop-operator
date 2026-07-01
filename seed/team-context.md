# Team context — who's who + risk rules

Loop uses this file (in `/knowledge`) to resolve owners and set risk. Keep it short and current.

## People
- **Priya** — Design lead. Owns design and the customer-facing deck. Historically slips deck deadlines.
- **Marco** — Backend. Owns API, data pipeline, and infra.
- **Dana** — Growth / partnerships. Owns customer and vendor communication.
- **Sam** — Founder / organizer. Runs standups; final approver for external and financial commitments.

## Owner resolution hints
- "the deck", "design", "mocks" -> Priya
- "API", "endpoint", "pipeline", "infra", "migration" -> Marco
- "customer", "vendor", "contract", "partner", "email them" -> Dana
- "budget", "spend", "pricing", "invoice" -> Sam

## Risk rules (override the model)
- Anything **external** (customer/vendor/partner), **financial**, **legal**, or a **public promise** = HIGH risk.
- A HIGH-risk item must be **human-confirmed** before Loop sends anything externally.
- Internal engineering tasks default to LOW/MEDIUM unless they block a customer commitment.

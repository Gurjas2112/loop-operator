#input_type_name: PersistInput
#output_type_name: PersistResult
#function_name: persist_items
#python_packages: structlog

import structlog
from pydantic import BaseModel
from typing import Any
from lemma_sdk import FunctionContext, Pod

log = structlog.get_logger()


class PersistInput(BaseModel):
    meeting_id: str
    items: list[dict[str, Any]]
    summary: str | None = None


class PersistResult(BaseModel):
    created: int
    needs_confirmation: bool
    organizer_member_id: str | None = None


def _metric(pod, name, value, labels=None):
    pod.table("metrics").create({"name": name, "value": float(value), "labels": labels or {}})


def _fuzzy_key(title: str) -> str:
    # Stable short key used to match a new item against an existing open commitment.
    return (title or "").lower().strip()[:40]


def _link_commitment(pod, it, meeting_id):
    owner = it.get("owner_user_id")
    if not owner:
        return None
    key = _fuzzy_key(it.get("title") or "")
    rows = pod.query(
        "select id, title, times_recommitted from commitments "
        f"where owner_user_id = '{owner}' and current_status = 'open'"
    ).to_dict()["items"]
    for c in rows:
        existing = (c.get("title") or "").lower()
        if key and key[:20] and key[:20] in existing:
            pod.table("commitments").update(
                c["id"], {"times_recommitted": (c.get("times_recommitted") or 1) + 1}
            )
            return c["id"]
    created = pod.table("commitments").create({
        "title": it["title"],
        "owner_user_id": owner,
        "first_seen_meeting_id": meeting_id,
        "times_recommitted": 1,
        "current_status": "open",
    })
    return created["id"]


async def persist_items(ctx: FunctionContext, data: PersistInput) -> PersistResult:
    pod = Pod.from_env()
    meeting = pod.table("meetings").get(data.meeting_id)
    needs = False
    created = 0

    for it in data.items:
        low_conf = float(it.get("confidence") or 0) < 0.6
        unowned = not it.get("owner_user_id")
        high_risk = it.get("risk") == "high"
        status = "proposed" if (low_conf or unowned or high_risk) else "confirmed"
        needs = needs or low_conf or unowned or high_risk

        commitment_id = _link_commitment(pod, it, data.meeting_id)
        row = pod.table("action_items").create({
            "meeting_id": data.meeting_id,
            "title": it["title"],
            "kind": it.get("kind", "task"),
            "owner_user_id": it.get("owner_user_id"),
            "owner_hint": it.get("owner_hint"),
            "due_date": it.get("due_date"),
            "status": status,
            "risk": it.get("risk", "low"),
            "confidence": it.get("confidence"),
            "source_quote": it.get("source_quote"),
            "source_page": it.get("source_page"),
            "commitment_id": commitment_id,
        })
        pod.table("activity_log").create({
            "action_item_id": row["id"],
            "kind": "extracted",
            "note": (it.get("source_quote") or "")[:280],
            "actor": ctx.user_id,
        })
        created += 1

    if data.summary:
        pod.table("meetings").update(data.meeting_id, {"summary": data.summary, "status": "ready"})

    _metric(pod, "items_extracted", created, {"meeting_id": data.meeting_id})
    log.info("persisted", meeting=data.meeting_id, created=created, needs_confirmation=needs)

    return PersistResult(
        created=created,
        needs_confirmation=needs,
        organizer_member_id=(meeting or {}).get("organizer_user_id"),
    )

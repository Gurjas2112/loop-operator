#input_type_name: ReplyInput
#output_type_name: ReplyResult
#function_name: record_reply
#python_packages: structlog

import re

from pydantic import BaseModel
from lemma_sdk import FunctionContext, Pod

try:  # structlog installs from #python_packages before real runs; stay import-safe during schema extraction
    import structlog
    log = structlog.get_logger()
except ModuleNotFoundError:
    import logging
    log = logging.getLogger("loop")


class ReplyInput(BaseModel):
    item_number: int
    reply: str


class ReplyResult(BaseModel):
    item_number: int
    status: str | None = None
    due_date: str | None = None
    matched: bool = False


def parse_reply(reply: str) -> dict:
    # Pure, unit-tested: map a free-text owner reply to a status/due-date update.
    r = (reply or "").strip().lower()
    slip = re.search(r"slip(?:ping)?\s+to\s+([0-9]{4}-[0-9]{2}-[0-9]{2})", r)
    if slip:
        return {"status": "in_progress", "due_date": slip.group(1)}
    if "done" in r or "complete" in r or "finished" in r:
        return {"status": "done"}
    if "blocked" in r or "stuck" in r:
        return {"status": "blocked"}
    if "dropp" in r or "cancel" in r or "won't" in r or "wont" in r:
        return {"status": "dropped"}
    if "in progress" in r or "working" in r or "started" in r:
        return {"status": "in_progress"}
    return {}


async def record_reply(ctx: FunctionContext, data: ReplyInput) -> ReplyResult:
    pod = Pod.from_env()
    rows = pod.records.list(
        "action_items", limit=1,
        filter=[{"field": "number", "op": "eq", "value": data.item_number}],
    ).to_dict()["items"]
    if not rows:
        return ReplyResult(item_number=data.item_number, matched=False)

    item = rows[0]
    update = parse_reply(data.reply)
    if not update:
        return ReplyResult(item_number=data.item_number, matched=False)

    pod.table("action_items").update(item["id"], update)
    pod.table("activity_log").create({
        "action_item_id": item["id"],
        "kind": "replied",
        "note": f"Owner reply: {data.reply[:200]}",
        "actor": ctx.user_id,
    })
    if "status" in update:
        pod.table("activity_log").create({
            "action_item_id": item["id"],
            "kind": "status_changed",
            "note": f"-> {update['status']}",
            "actor": "operator",
        })

    log.info("record_reply", number=data.item_number, update=update)
    return ReplyResult(
        item_number=data.item_number,
        status=update.get("status"),
        due_date=update.get("due_date"),
        matched=True,
    )

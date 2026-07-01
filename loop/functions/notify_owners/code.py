#input_type_name: NotifyInput
#output_type_name: NotifyResult
#function_name: notify_owners
#python_packages: structlog

from datetime import datetime, timezone

import structlog
from pydantic import BaseModel
from lemma_sdk import FunctionContext, Pod

log = structlog.get_logger()

# Confirm the exact Slack operation id for your provider with:
#   lemma connectors operations search workspace-slack "post message"
SLACK_AUTH_CONFIG = "workspace-slack"
SLACK_POST_OP = "chat_post_message"


class NotifyInput(BaseModel):
    meeting_id: str


class NotifyResult(BaseModel):
    notified: int
    blocked: int


def _resolve_slack(pod, owner_user_id):
    # user_prefs is RLS-scoped to the invoking user, so we see the demo user's row(s).
    prefs = pod.records.list("user_prefs", limit=200).to_dict()["items"]
    by_user = {p.get("user_id"): p.get("slack_user_id") for p in prefs if p.get("slack_user_id")}
    default_slack = next((p.get("slack_user_id") for p in prefs if p.get("slack_user_id")), None)
    return by_user.get(owner_user_id) or default_slack


def _message(item):
    due = item.get("due_date") or "no date"
    return (
        f":loop: *Loop nudge* — you own action item #{item.get('number')}: "
        f"*{item.get('title')}* (due {due}, risk {item.get('risk')}).\n"
        f"Reply here: `done`, `blocked`, `in progress`, `slipping to <date>`, or `dropped`."
    )


async def notify_owners(ctx: FunctionContext, data: NotifyInput) -> NotifyResult:
    pod = Pod.from_env()
    items = pod.records.list(
        "action_items",
        limit=200,
        filter=[
            {"field": "meeting_id", "op": "eq", "value": data.meeting_id},
            {"field": "status", "op": "eq", "value": "confirmed"},
        ],
    ).to_dict()["items"]

    notified = 0
    blocked = 0
    for item in items:
        slack_id = _resolve_slack(pod, item.get("owner_user_id"))
        if not slack_id:
            continue

        msg = _message(item)
        gate = pod.functions.run("policy_gate", {
            "text": msg,
            "action": "external_send",
            "item": item,
        }).to_dict()["output_data"] or {}
        if not gate.get("allowed", False):
            blocked += 1
            continue

        text = gate.get("redacted_text") or msg
        pod.connectors.execute(SLACK_AUTH_CONFIG, SLACK_POST_OP, {"channel": slack_id, "text": text})

        now = datetime.now(timezone.utc).isoformat()
        pod.table("action_items").update(item["id"], {
            "nudge_count": (item.get("nudge_count") or 0) + 1,
            "last_nudged_at": now,
        })
        pod.table("activity_log").create({
            "action_item_id": item["id"],
            "kind": "nudged",
            "note": f"Slack nudge sent to owner ({slack_id}).",
            "actor": "operator",
        })
        pod.table("metrics").create({"name": "nudges_sent", "value": 1.0, "labels": {"meeting_id": data.meeting_id}})
        notified += 1

    log.info("notify_owners", meeting=data.meeting_id, notified=notified, blocked=blocked)
    return NotifyResult(notified=notified, blocked=blocked)

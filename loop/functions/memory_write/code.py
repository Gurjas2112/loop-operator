#input_type_name: MemoryInput
#output_type_name: MemoryResult
#function_name: memory_write
#python_packages: structlog

import re
from datetime import datetime, timezone

from pydantic import BaseModel
from typing import Any
from lemma_sdk import FunctionContext, Pod

try:  # structlog installs from #python_packages before real runs; stay import-safe during schema extraction
    import structlog
    log = structlog.get_logger()
except ModuleNotFoundError:
    import logging
    log = logging.getLogger("loop")


class MemoryInput(BaseModel):
    facts: list[dict[str, Any]]


class MemoryResult(BaseModel):
    written: int
    files_touched: int


def slugify(subject: str) -> str:
    # Pure, unit-tested: stable file slug per subject.
    s = (subject or "unknown").strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "unknown"


def upsert_fact(pod, fact: dict) -> bool:
    # Returns True if a NEW row was created (statement changed / not seen before).
    subject = fact["subject"]
    kind = fact["kind"]
    statement = fact["statement"]
    now = datetime.now(timezone.utc).isoformat()

    existing = pod.records.list(
        "memory", limit=50,
        filter=[
            {"field": "subject", "op": "eq", "value": subject},
            {"field": "kind", "op": "eq", "value": kind},
        ],
    ).to_dict()["items"]
    live = [m for m in existing if not m.get("superseded_by")]

    for m in live:
        if (m.get("statement") or "").strip() == statement.strip():
            pod.table("memory").update(m["id"], {"last_seen_at": now})
            return False

    new_row = pod.table("memory").create({
        "subject": subject,
        "kind": kind,
        "statement": statement,
        "confidence": fact.get("confidence", 0.7),
        "source_meeting_id": fact.get("source_meeting_id"),
        "last_seen_at": now,
    })
    # A changed statement supersedes the prior live row of the same (subject, kind).
    for m in live:
        pod.table("memory").update(m["id"], {"superseded_by": new_row["id"]})
    return True


async def memory_write(ctx: FunctionContext, data: MemoryInput) -> MemoryResult:
    pod = Pod.from_env()
    written = 0
    files = set()

    for fact in data.facts:
        created = upsert_fact(pod, fact)
        if created:
            written += 1
        # Append a semantic bullet so Lemma's built-in index makes it searchable.
        # append_text creates the file if absent (read-modify-write).
        path = f"/memory/{slugify(fact['subject'])}.md"
        bullet = f"- ({fact['kind']}) {fact['statement']}\n"
        pod.files.append_text(path, bullet)
        files.add(path)

    pod.table("metrics").create({"name": "memory_facts_written", "value": float(written), "labels": {}})
    log.info("memory_write", written=written, files=len(files))
    return MemoryResult(written=written, files_touched=len(files))

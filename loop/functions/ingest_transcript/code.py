#input_type_name: IngestInput
#output_type_name: IngestResult
#function_name: ingest_transcript
#python_packages: structlog

import hashlib
from pydantic import BaseModel
from lemma_sdk import FunctionContext, Pod

try:  # structlog installs from #python_packages before real runs; stay import-safe during schema extraction
    import structlog
    log = structlog.get_logger()
except ModuleNotFoundError:
    import logging
    log = logging.getLogger("loop")


class IngestInput(BaseModel):
    title: str
    transcript_text: str
    organizer_user_id: str | None = None
    source: str = "upload"


class IngestResult(BaseModel):
    meeting_id: str
    transcript_path: str
    sha: str


async def ingest_transcript(ctx: FunctionContext, data: IngestInput) -> IngestResult:
    pod = Pod.from_env()
    sha = hashlib.sha256(data.transcript_text.encode("utf-8")).hexdigest()
    path = f"/transcripts/{sha}.md"

    # Store the transcript so Lemma auto-indexes it -> semantic provenance + page markers.
    pod.files.write_text(path, data.transcript_text)

    meeting = pod.table("meetings").create({
        "title": data.title,
        "source": data.source,
        "transcript_path": path,
        "transcript_sha": sha,
        "organizer_user_id": data.organizer_user_id or ctx.user_id,
        "status": "ingested",
    })

    log.info("ingested", meeting=meeting["id"], sha=sha, path=path)
    return IngestResult(meeting_id=str(meeting["id"]), transcript_path=path, sha=sha)

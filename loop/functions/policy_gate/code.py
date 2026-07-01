#input_type_name: PolicyInput
#output_type_name: PolicyResult
#function_name: policy_gate
#python_packages: presidio-analyzer, presidio-anonymizer, structlog

from pydantic import BaseModel
from typing import Any
from lemma_sdk import FunctionContext, Pod

try:  # structlog installs from #python_packages before real runs; stay import-safe during schema extraction
    import structlog
    log = structlog.get_logger()
except ModuleNotFoundError:
    import logging
    log = logging.getLogger("loop")

# Lazily initialized so import stays cheap and the first call warms the models.
_analyzer = None
_anonymizer = None


def _engines():
    global _analyzer, _anonymizer
    if _analyzer is None:
        from presidio_analyzer import AnalyzerEngine
        from presidio_anonymizer import AnonymizerEngine
        _analyzer = AnalyzerEngine()
        _anonymizer = AnonymizerEngine()
    return _analyzer, _anonymizer


def redact(text: str) -> tuple[str, bool]:
    if not text:
        return text, False
    analyzer, anonymizer = _engines()
    results = analyzer.analyze(text=text, language="en")
    if not results:
        return text, False
    out = anonymizer.anonymize(text=text, analyzer_results=results).text
    return out, out != text


def decide(action: str, item: dict[str, Any]) -> tuple[bool, str]:
    # The core policy: external high-risk sends must be human-confirmed first.
    if action == "external_send" and item.get("risk") == "high" and item.get("status") != "confirmed":
        return False, "High-risk external send blocked until the item is confirmed by a human."
    return True, "ok"


class PolicyInput(BaseModel):
    text: str = ""
    action: str = "external_send"
    item: dict[str, Any] = {}


class PolicyResult(BaseModel):
    allowed: bool
    redacted_text: str
    reason: str


async def policy_gate(ctx: FunctionContext, data: PolicyInput) -> PolicyResult:
    pod = Pod.from_env()
    redacted_text, changed = redact(data.text)
    allowed, reason = decide(data.action, data.item or {})

    if changed:
        pod.table("activity_log").create({
            "action_item_id": (data.item or {}).get("id"),
            "kind": "redacted",
            "note": "PII redacted before external send.",
            "actor": "operator",
        })
        pod.table("metrics").create({"name": "pii_redactions", "value": 1.0, "labels": {"action": data.action}})

    if not allowed:
        pod.table("metrics").create({"name": "policy_blocks", "value": 1.0, "labels": {"action": data.action}})

    log.info("policy_gate", allowed=allowed, changed=changed, action=data.action)
    return PolicyResult(allowed=allowed, redacted_text=redacted_text, reason=reason)

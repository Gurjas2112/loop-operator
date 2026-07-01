"""Unit tests for the PURE helpers inside Loop's functions.

These test logic that does not touch the pod (no Pod.from_env), so they run with
plain pytest on your machine:  uv pip install pytest  &&  pytest tests/test_functions.py

They import the helpers directly from each function's code.py by file path, so no
package install of the bundle is needed.
"""
import importlib.util
import pathlib
import sys
import types

ROOT = pathlib.Path(__file__).resolve().parents[1] / "loop" / "functions"


def _stub_sandbox_modules():
    """The functions import `lemma_sdk` (and lazily presidio) which only exist in
    the pod sandbox. Stub the sandbox-only modules so the PURE helpers import here."""
    if "lemma_sdk" not in sys.modules:
        m = types.ModuleType("lemma_sdk")
        m.FunctionContext = object
        m.Pod = object
        sys.modules["lemma_sdk"] = m
    if "structlog" not in sys.modules:
        try:
            import structlog  # noqa: F401
        except Exception:
            s = types.ModuleType("structlog")
            s.get_logger = lambda *a, **k: types.SimpleNamespace(info=lambda *a, **k: None)
            sys.modules["structlog"] = s


def _load(name):
    _stub_sandbox_modules()
    path = ROOT / name / "code.py"
    spec = importlib.util.spec_from_file_location(f"loop_{name}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---- record_reply.parse_reply -------------------------------------------------
record_reply = _load("record_reply")


def test_reply_done():
    assert record_reply.parse_reply("all done!")["status"] == "done"


def test_reply_blocked():
    assert record_reply.parse_reply("I'm blocked on infra")["status"] == "blocked"


def test_reply_in_progress():
    assert record_reply.parse_reply("working on it")["status"] == "in_progress"


def test_reply_dropped():
    assert record_reply.parse_reply("we're dropping this")["status"] == "dropped"


def test_reply_slipping_with_date():
    out = record_reply.parse_reply("slipping to 2026-07-20")
    assert out["status"] == "in_progress"
    assert out["due_date"] == "2026-07-20"


def test_reply_unrecognized():
    assert record_reply.parse_reply("hmm maybe later") == {}


# ---- policy_gate.decide (the guardrail rule) ----------------------------------
policy_gate = _load("policy_gate")


def test_policy_blocks_high_risk_unconfirmed_external():
    allowed, _ = policy_gate.decide("external_send", {"risk": "high", "status": "proposed"})
    assert allowed is False


def test_policy_allows_high_risk_when_confirmed():
    allowed, _ = policy_gate.decide("external_send", {"risk": "high", "status": "confirmed"})
    assert allowed is True


def test_policy_allows_low_risk():
    allowed, _ = policy_gate.decide("external_send", {"risk": "low", "status": "proposed"})
    assert allowed is True


def test_policy_allows_internal_action():
    allowed, _ = policy_gate.decide("internal_note", {"risk": "high", "status": "proposed"})
    assert allowed is True


# ---- persist_items._fuzzy_key (commitment matching) --------------------------
persist_items = _load("persist_items")


def test_fuzzy_key_truncates_and_lowercases():
    key = persist_items._fuzzy_key("  Deliver The Icon Set For The Customer Deck Immediately  ")
    assert key == "deliver the icon set for the customer d"
    assert key == key.lower()


def test_fuzzy_key_prefix_matches_recommitment():
    a = persist_items._fuzzy_key("Deliver the icon set")
    b = persist_items._fuzzy_key("Deliver the icon set for the deck")
    # The 20-char prefix used by _link_commitment matches across recommitments.
    assert a[:20] in b


# ---- memory_write.slugify -----------------------------------------------------
memory_write = _load("memory_write")


def test_slugify_basic():
    assert memory_write.slugify("Priya") == "priya"


def test_slugify_spaces_and_punct():
    assert memory_write.slugify("Acme Corp / Renewal!") == "acme-corp-renewal"


def test_slugify_empty():
    assert memory_write.slugify("") == "unknown"

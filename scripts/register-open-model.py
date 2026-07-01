#!/usr/bin/env python3
"""Register a local open-source model (via Ollama) as a Lemma runtime profile
and pin it on every Loop agent.

Why this exists
---------------
Loop's agents (extractor / operator / reconciler / librarian / desk) only need
two capabilities from their model: reliable structured-JSON output and function
(tool) calling. Open instruction-tuned models handle both well, so Loop can run
fully local with zero per-token cost and no data leaving the machine.

Lemma accepts any OpenAI-compatible endpoint. Ollama exposes exactly that at
`/v1`, so we register an OPENAI_COMPATIBLE runtime profile that points at it and
then write the returned profile id into each agent's `agent_runtime` block.

Prerequisites
-------------
  1. `ollama serve` running with a chat model pulled (see scripts/setup-open-model.md).
  2. The Lemma stack up and this shell authenticated (LEMMA_TOKEN / LEMMA_BASE_URL
     / LEMMA_ORG_ID present — a `lemma` workspace session injects these).
  3. `pip install lemma-sdk` (the same SDK the functions use).

Usage
-----
  python scripts/register-open-model.py                 # register + pin (defaults)
  python scripts/register-open-model.py --no-write      # register only, print the block
  MODEL=qwen2.5:7b-instruct python scripts/register-open-model.py

The base URL defaults to `host.docker.internal` because the Lemma agent runtime
runs inside Docker and must reach Ollama on the host. Override with BASE_URL for
a bare-metal runtime (`http://localhost:11434/v1`).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

MODEL = os.environ.get("MODEL", "qwen2.5:3b-instruct")
BASE_URL = os.environ.get("BASE_URL", "http://host.docker.internal:11434/v1")
PROFILE_NAME = os.environ.get("PROFILE_NAME", "loop-local-open")
# Ollama ignores the key, but the OpenAI client requires a non-empty string.
API_KEY = os.environ.get("OLLAMA_API_KEY", "ollama-local")

AGENTS_DIR = Path(__file__).resolve().parent.parent / "loop" / "agents"
AGENT_NAMES = ["extractor", "operator", "reconciler", "librarian", "desk"]


def register_profile() -> str:
    """Create (or reuse) the OpenAI-compatible profile and return its id."""
    try:
        from lemma_sdk import Pod  # type: ignore
    except Exception as exc:  # pragma: no cover - depends on install
        sys.exit(
            "lemma-sdk is not importable ({}). Run `pip install lemma-sdk` in the "
            "same environment the Lemma workspace session set up.".format(exc)
        )

    pod = Pod.from_env()

    existing = pod.org_runtime.profiles()
    for p in getattr(existing, "profiles", None) or getattr(existing, "items", []) or []:
        if getattr(p, "name", None) == PROFILE_NAME:
            pid = str(getattr(p, "id", "") or getattr(p, "uuid", ""))
            print(f"Reusing existing profile '{PROFILE_NAME}' -> {pid}")
            return pid

    created = pod.org_runtime.create_profile(
        {
            "source": "OPENAI_COMPATIBLE",
            "name": PROFILE_NAME,
            "description": "Local open-source model served by Ollama for Loop agents.",
            "base_url": BASE_URL,
            "default_model_name": MODEL,
            "model_names": [MODEL],
            "api_key": API_KEY,
        }
    )
    pid = str(getattr(created, "id", "") or getattr(created, "uuid", ""))
    print(f"Created profile '{PROFILE_NAME}' -> {pid}  (model={MODEL}, base={BASE_URL})")
    return pid


def pin_on_agents(profile_id: str) -> None:
    """Insert/replace the `agent_runtime` block in each agent's JSON bundle file."""
    block = f'  "agent_runtime": {{ "profile_id": "{profile_id}", "model_name": "{MODEL}" }},'
    for name in AGENT_NAMES:
        path = AGENTS_DIR / name / f"{name}.json"
        if not path.exists():
            print(f"  ! skip {name}: {path} not found")
            continue
        text = path.read_text(encoding="utf-8")
        if '"agent_runtime"' in text:
            text = re.sub(
                r'[ \t]*"agent_runtime"\s*:\s*\{[^}]*\},?',
                block.strip(),
                text,
                count=1,
            )
        else:
            # Insert right after the object's opening brace line.
            text = re.sub(r'(\n\{\n)', r"\1" + block + "\n", text, count=1)
        path.write_text(text, encoding="utf-8")
        print(f"  pinned {name}")
    print("\nRe-import the agents so the platform picks up the runtime:")
    print("  lemma pods import ./loop --only agents   # or: lemma pods import ./loop")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--no-write", action="store_true", help="register only; don't edit agent files")
    args = ap.parse_args()

    profile_id = register_profile()

    if args.no_write:
        print("\nPin this on each agent JSON (agent_runtime):")
        print(json.dumps({"profile_id": profile_id, "model_name": MODEL}, indent=2))
        return

    pin_on_agents(profile_id)


if __name__ == "__main__":
    main()

# Run Loop on an open-source model (local, zero-cost)

Loop's agents need only two things from their LLM: **structured-JSON output** and
**function/tool calling**. Modern open instruction-tuned models do both well, so
Loop can run **fully local** — no API key, no per-token cost, and no transcript
data leaving the machine. This is the recommended default for demos and for any
privacy-sensitive deployment.

Lemma accepts **any OpenAI-compatible endpoint** for an agent runtime. [Ollama](https://ollama.com)
exposes exactly that at `http://localhost:11434/v1`, so wiring it up is three steps.

## Is an open model "good enough" here?

Yes, for Loop's workload:

| Loop agent   | What the model must do                              | Open-model fit |
| ------------ | -------------------------------------------------- | -------------- |
| `extractor`  | Emit a strict `items[]` JSON schema, cite quotes   | Strong         |
| `desk`       | Call granted functions (`record_reply`, search)    | Strong         |
| `operator`   | Short reasoning + tool calls (nudge/escalate)      | Strong         |
| `reconciler` | Compare records, flag contradictions               | Good           |
| `librarian`  | Summarize into memory facts                         | Good           |

The heavy lifting (provenance, SLA math, PII redaction, fuzzy commitment linking)
lives in **deterministic Python functions**, not the model — so a small local
model is enough to drive the judgment layer.

### Recommended models (tool-calling capable)

| Model                    | `ollama pull`                 | Notes                                   |
| ------------------------ | ----------------------------- | --------------------------------------- |
| Qwen2.5 3B Instruct      | `qwen2.5:3b-instruct`         | Already installed here; fast, laptop-ok |
| Qwen2.5 7B Instruct      | `qwen2.5:7b-instruct`         | Better JSON reliability (recommended)   |
| Qwen2.5 14B Instruct     | `qwen2.5:14b-instruct`        | Best quality if you have the RAM/VRAM   |
| Llama 3.1 8B Instruct    | `llama3.1:8b-instruct`        | Solid alternative                       |

Embeddings for the `/transcripts`, `/knowledge`, `/memory` RAG folders are handled
separately by the platform; `nomic-embed-text` (already installed) is a good local
embedding model if the stack asks for one.

## Step 1 — Pull a model and start Ollama

```bash
ollama pull qwen2.5:7b-instruct     # or use the installed qwen2.5:3b-instruct
ollama serve                        # usually already running as a service
curl http://localhost:11434/v1/models   # sanity check the OpenAI-compatible API
```

## Step 2 — Register it as a Lemma runtime profile and pin it on the agents

The Lemma agent runtime runs **inside Docker**, so it reaches host Ollama at
`host.docker.internal`, not `localhost`. The helper script handles this:

```bash
# from the repo root, in a shell where the Lemma workspace session is active
pip install lemma-sdk
python scripts/register-open-model.py                 # defaults to qwen2.5:3b-instruct
# or pick a model / endpoint:
MODEL=qwen2.5:7b-instruct python scripts/register-open-model.py
BASE_URL=http://localhost:11434/v1 python scripts/register-open-model.py   # bare-metal runtime
```

The script creates an `OPENAI_COMPATIBLE` profile (`loop-local-open`) and writes
`agent_runtime: { profile_id, model_name }` into all five agent JSON files.

Prefer to do it by hand? The equivalent SDK call is:

```python
from lemma_sdk import Pod
Pod.from_env().org_runtime.create_profile({
    "source": "OPENAI_COMPATIBLE",
    "name": "loop-local-open",
    "base_url": "http://host.docker.internal:11434/v1",
    "default_model_name": "qwen2.5:7b-instruct",
    "model_names": ["qwen2.5:7b-instruct"],
    "api_key": "ollama-local",   # ignored by Ollama, required by the client
})
```

Then add this to each `loop/agents/<name>/<name>.json` (top of the object):

```jsonc
"agent_runtime": { "profile_id": "<profile-id>", "model_name": "qwen2.5:7b-instruct" },
```

## Step 3 — Re-import and test

```bash
lemma pods import ./loop
lemma agents run extractor "Extract action items: 'Priya will send the SOC2 draft by Friday.'"
```

Check that the JSON schema comes back populated and quotes are cited. If a small
model struggles with strict schema output, step up one size (3B -> 7B -> 14B).

## Hosted OpenAI-compatible alternatives

The same profile works against any OpenAI-compatible gateway if you'd rather not
run locally — set `base_url` + `api_key` to a provider that serves open models
(e.g. Groq, Together, Fireworks) or your own vLLM/LM Studio server. Only the two
fields change; the agent wiring is identical.

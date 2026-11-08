# Appendix — Local Setup with Ollama & pgvector

> Reference appendix. This is required pre-work for the live session (see
> [[Pre-Session E-Learning]]). Everything runs locally: no API keys, no accounts, no cost.
>
> In total: about **6 GB of model downloads** and five commands. The downloads are the
> slow part, so start them the day before, not an hour before.

---

## What You Need

| Requirement | Version | Note |
|---|---|---|
| Python | 3.10+ | 3.12 is the program baseline (fittingly, that's `adr-0002` in the demo corpus) |
| Docker | any recent | with the Compose plugin |
| Ollama | 0.24+ | `curl -fsSL https://ollama.com/install.sh \| sh` |
| Disk | ~8 GB | 6 GB models + Postgres volume |
| GPU | optional | works on CPU; every timing in the lecture is from a laptop RTX 4060 |

Measured on that laptop: a `naive` query takes 0.12 s and a full `result` query about
4 s. On CPU only, expect roughly 3–5× that. Everything still works, just slower.

---

## Step 1 — Models

```bash
ollama pull embeddinggemma:300m     # 621 MB — embeddings, 768 dimensions
ollama pull qwen2.5:7b-instruct     # 4.7 GB — chat, tool calling, reranking
```

Verify:

```bash
ollama list
# NAME                   SIZE
# qwen2.5:7b-instruct    4.7 GB
# embeddinggemma:300m    621 MB
```

> [!warning] The chat model must not be a reasoning model
> On a laptop, the obvious pick is a small reasoning model like `qwen3:4b`. Don't use one
> here. This isn't a matter of taste; we measured it.
>
> A retrieval pipeline makes a dozen small extraction and scoring calls per question: pull
> two filters out of a sentence, write three paraphrases, score one passage 0–10. A
> reasoning model spends 1,000–2,500 tokens thinking before it writes any of them. On the
> exact same prompt: **648 ms with `qwen2.5:7b-instruct`, 20 s with `qwen3:4b`**. One seed
> run went from 70 seconds to over 40 minutes.
>
> Limiting output tokens doesn't fix it. The thinking uses up the limit and the answer
> comes back empty. That's worse than slow, because it fails silently. Reasoning models are
> worth it for one hard answer, not for twelve small ones.
>
> If you want an alternative: `llama3.1:8b` and `mistral-nemo` both work. `llama3.2:3b` is
> fast but too weak. It scored only 1 of 3 passages in a rerank batch and completely
> misunderstood the routing task.

---

## Step 2 — Postgres with pgvector

```bash
cd examples
docker compose up -d
```

```yaml
services:
  postgres:
    image: pgvector/pgvector:pg17
    container_name: docs-assistant-pg
    environment:
      POSTGRES_DB: docs_assistant
      POSTGRES_USER: docs
      POSTGRES_PASSWORD: docs
    ports:
      - '5434:5432'
```

Port **5434**, not 5432 or 5433, because those clash with a local Postgres and with other
projects. The `pgvector/pgvector:pg17` image includes the extension, so `CREATE EXTENSION
vector` in the schema is all you need.

Verify:

```bash
docker exec docs-assistant-pg pg_isready -U docs -d docs_assistant
# /var/run/postgresql:5432 - accepting connections
```

---

## Step 3 — Python Environment

```bash
python3 -m venv .venv
.venv/bin/pip install -e .
cp .env.example .env
```

Only four dependencies, on purpose: `ollama`, `psycopg[binary]`, `python-dotenv`,
`pyyaml`. No LangChain, no LlamaIndex, no `sentence-transformers`. The point of the project
is to show how things work inside, and the whole install takes under 30 seconds.

`.env` defaults:

```
DATABASE_URL=postgresql://docs:docs@localhost:5434/docs_assistant
OLLAMA_HOST=http://localhost:11434
EMBEDDING_MODEL=embeddinggemma:300m
EMBEDDING_DIMENSIONS=768
CHAT_MODEL=qwen2.5:7b-instruct
MAX_AGENT_ITERATIONS=6
```

---

## Step 4 — Seed the Index

```bash
.venv/bin/python scripts/seed.py --reset
```

```
resetting schema
41 documents | embeddings embeddinggemma:300m | contextual prefixes off
warming up ollama (the first call loads the model into memory)
  embed: 120/120 chunks      3s
ingested 41 documents / 120 chunks in 3.5s (skipped 0 unchanged)
index now holds 41 documents / 120 chunks
```

**3.5 seconds.** Running it again with no changes costs nothing, because the content hash
skips everything:

```
ingested 0 documents / 0 chunks in 0.0s (skipped 41 unchanged)
```

The contextual-prefix version from section 05 is a separate, slower run. Don't do it as
part of setup. It's an experiment to run *during* section 05:

```bash
.venv/bin/python scripts/seed.py --reset --contextual --concurrency 6
#   context: 120/120 chunks    64s
#   embed:   120/120 chunks    70s
```

64 seconds for 120 LLM calls, six at a time. One after another, it takes over 40
minutes. Running them in parallel isn't just an optimisation here. It's what makes the
technique possible to test at all.

To get back to the plain index afterwards: `scripts/seed.py --reset`.

---

## Step 5 — Verify Everything Works

Run these in order. If all five work as shown, you're ready for the session.

```bash
# 1. Ungrounded baseline — a confident, invented answer (section 01)
.venv/bin/python scripts/ask.py --mode none "Why does checkout-svc return 502 after the v4 migration?"

# 2. Naive RAG — grounded, cited, ~0.12s retrieval (section 03)
.venv/bin/python scripts/ask.py --mode naive "how do I roll back a checkout deploy"

# 3. The refusal path — must say "I don't have that in the docs." (section 03)
.venv/bin/python scripts/ask.py --mode naive "what is our kubernetes cluster autoscaler configuration?"

# 4. The full result-side pipeline, with the trace (sections 04-05)
.venv/bin/python scripts/ask.py --mode result "why is it 502ing?"

# 5. The benchmark — this is the number the whole lecture is built on (section 07)
.venv/bin/python scripts/bench.py --modes naive --top-k 5
```

Expected from step 5:

```
naive     recall@5 = 0.76     median 0.12s     p95 0.13s
```

If you get 0.76, your setup matches the one used for every number in the lecture.

Optional, but worth seeing at least once:

```bash
# The agent tool loop, with per-iteration token accounting (sections 01-02)
.venv/bin/python scripts/trace_agent.py "compare how checkout and notify handle retries, name the ADR that governs each, and say who owns those services"

# Routing decisions (section 06)
.venv/bin/python scripts/ask.py --mode route "what python version do we target"

# Permission-aware retrieval (section 07)
.venv/bin/python scripts/ask.py --mode result "what did the Q2 penetration test find?"
.venv/bin/python scripts/ask.py --mode result "what did the Q2 penetration test find?" --as security-team
```

The last pair is the one to really try: the same question returns a restricted
postmortem only for the second caller.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `ModuleNotFoundError: No module named '_ctypes'` | A pyenv Python built without libffi — `psycopg` can't load | Use the system Python, or rebuild after `apt install libffi-dev` |
| First call takes 45 s, later ones take 1 s | The model is loading into VRAM for the first time | Expected. That's why `scripts/seed.py` calls `warm_up()` first. Before the live session, run any query once |
| `connection refused` on port 5434 | Container not running, or the port is taken | `docker compose ps`; `ss -tlnp \| grep 5434` |
| `type "vector" does not exist` | Wrong Postgres image | Must be `pgvector/pgvector:pg17`. `docker compose down -v` and up again |
| `expected 768 dimensions, not N` | Embedding model changed | The schema pins `vector(768)`. Re-seed with `--reset` after any model change |
| Every rerank score is `0` | The chat model isn't following the format | `_is_degenerate()` catches this and keeps the fused order. If it keeps happening, your chat model is too small |
| Answers have no `[doc-id]` citations | Model ignoring the contract | Expected with weaker models — the example in `GROUNDING_CONTRACT` is what fixes it. See §03 |
| Answers are 300 words of headings and numbered plans | Same cause | Rule 5 plus the example. Without an example, the model tends to ignore the rule |
| Everything is 20× slower than the quoted numbers | You're using a reasoning model | Check `CHAT_MODEL`. See the warning in step 1 |
| `bench.py` recall differs run to run | Expected | Only `naive` is deterministic. `query` and `result` call an LLM. See §07 on setting gate thresholds |

---

## Project Layout

```
examples/
├── docker-compose.yml          pgvector/pgvector:pg17 on port 5434
├── pyproject.toml              4 dependencies, no framework
├── corpus/                     41 documents — ADRs, runbooks, APIs, postmortems, policies
├── golden_set.json             25 questions, each labelled with the failure it exercises
├── docs_assistant/
│   ├── settings.py             env config
│   ├── ollama_client.py        embed / complete / chat_with_tools
│   ├── db.py                   schema + connection + vector literals
│   ├── ingest.py               parse → chunk → contextualise → embed → write
│   ├── generate.py             the grounding contract          §03
│   ├── pipeline.py             the three fixed pipelines       §03-05
│   ├── agent_minimal.py        the 15-line loop                §01
│   ├── agent.py                the hardened loop + tools       §02
│   ├── cache.py                embedding + retrieval caches    §07
│   └── retrieve/
│       ├── naive.py            embed → top-k                   §03
│       ├── query_side.py       rewrite / expand / HyDE / self-query   §04
│       ├── result_side.py      RRF / rerank / MMR / parent / reorder  §05
│       └── agentic.py          grade → re-query, and routing   §06
└── scripts/
    ├── seed.py                 corpus → pgvector
    ├── ask.py                  --mode none|naive|query|result|agentic|agent|minimal|route
    ├── bench.py                recall@k + latency, --min-recall gates CI
    └── trace_agent.py          per-iteration token accounting  §01
```

---

[[Pre-Session E-Learning]] · [[Appendix - Retrieval Techniques Cheat Sheet]] ·
[[01 - Agent Fundamentals]]

## Slides

Not a deck section. It's pre-work, shared with [[Pre-Session E-Learning]]. One slide near
the start of the deck should show the five check commands from step 5, so anyone who
skipped setup knows what they're missing.

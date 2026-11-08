> **Homework submission (Section 9), Vadym Semchenko.** My comparison of `naive`, `query`, `result` and
> `agentic` retrieval on two golden-set questions, plus a full golden-set benchmark and a model-swap
> bonus, is in **[HOMEWORK_REPORT.md](HOMEWORK_REPORT.md)**. Raw outputs from every run are in
> [`results/`](results/). Everything below this note is the course's original README.

# Internal Engineering Docs Assistant

The running example for the lecture **Agents, RAG fundamentals & Advanced Retrieval**.

An agent that answers questions about a made-up platform of seven services, using 41
documents: architecture decision records, runbooks, API references, incident postmortems
and platform policies. Everything runs locally: Ollama for the models, Postgres with
pgvector for the index. No API keys, no accounts, no cost.

**No retrieval framework.** Four dependencies (`ollama`, `psycopg`, `python-dotenv`,
`pyyaml`), hand-written SQL, and an agent loop you can read in one go. The point is to see
how it all works inside.

---

## Prepare

```bash
ollama pull embeddinggemma:300m     # 621 MB — embeddings, 768 dimensions
ollama pull qwen2.5:7b-instruct     # 4.7 GB — chat, tool calling, reranking

docker compose up -d                # pgvector on port 5434
python3 -m venv .venv
.venv/bin/pip install -e .
cp .env.example .env
.venv/bin/python scripts/seed.py --reset
```

The seed takes **3.5 seconds**. Running it again on an unchanged corpus costs nothing, because a content hash skips everything.

> [!warning] `CHAT_MODEL` must not be a reasoning model
> A retrieval pipeline makes a dozen small extraction and scoring calls per question. A
> reasoning model spends 1,000–2,500 tokens thinking before it writes each one. On the exact
> same prompt we measured **648 ms with `qwen2.5:7b-instruct` versus 20 s with `qwen3:4b`**.
> Limiting `num_predict` makes it worse: the thinking uses up the limit and the answer comes
> back empty. `llama3.1:8b` and `mistral-nemo` also work. `llama3.2:3b` is too weak.

Full setup notes and a troubleshooting table are in
`Appendix - Local Setup with Ollama & pgvector.md`.

---

## Walk the lecture

Run these in order. Each one matches a section of the lecture, and each one is clearly
better or worse than the last in a way you can point at.

### Section 01 — the problem

```bash
.venv/bin/python scripts/ask.py --mode none "Why does checkout-svc return 502 after the v4 migration?"
```

Four hundred words of solid, generic troubleshooting advice: check your config, review
your logs, restart the service, check firewall rules. Each item makes sense in *some*
system. None of them is the answer. The real cause is in `adr-0061`.

Then try `"What is the outbound HTTP retry budget for checkout-svc?"` and watch it tell you
to ask a colleague. The answer is a table in `adr-0055`.

### Sections 01–02 — the agent loop

```bash
# the fragile 15-line version: no ceiling, no progress check, results with no handles
.venv/bin/python scripts/ask.py --mode minimal "which services still use the deprecated v3 auth flow, and who owns them?"

# the hardened version: iteration ceiling, no-progress detection, errors as data
.venv/bin/python scripts/ask.py --mode agent "which services still use the deprecated v3 auth flow, and who owns them?"

# what the loop actually costs, per iteration
.venv/bin/python scripts/trace_agent.py "compare how checkout and notify handle retries, name the ADR that governs each, and say who owns those services"
```

The `agent` run will probably get the answer wrong: it makes up a filter and stops after
one lookup. That failure is why section 06 exists.

### Section 03 — naive RAG

```bash
.venv/bin/python scripts/ask.py --mode naive "how do I roll back a checkout deploy" --show-context
```

Grounded, cited, ~0.12 s. Notice that the superseded 2025 runbook shows up at rank 3.

The refusal path. This is behaviour we designed on purpose, not something you get by
default:

```bash
.venv/bin/python scripts/ask.py --mode naive "what is our kubernetes cluster autoscaler configuration?"
```

Where it breaks:

```bash
.venv/bin/python scripts/ask.py --mode naive "why is it 502ing?" --show-context
```

Five plausible passages about gateway errors. `adr-0061`, which explains the cause, is at rank
**32 of 120**.

### Sections 04–05 — the fixed pipelines

```bash
# rewrite + self-query filters + multi-query, union and dedupe
.venv/bin/python scripts/ask.py --mode query "why is it 502ing?"

# the above + RRF + pointwise rerank + MMR + parent expansion + attention reorder
.venv/bin/python scripts/ask.py --mode result "why is it 502ing?" --show-context
```

The trace lines above the results show the rewrite, the extracted filters, the
expansions, and how many chunks were looked at.

Section 05's contextual-retrieval experiment (~70 s, then `--reset` to go back):

```bash
.venv/bin/python scripts/seed.py --reset --contextual --concurrency 6
.venv/bin/python scripts/bench.py --modes naive --top-k 5
.venv/bin/python scripts/seed.py --reset
```

### Section 06 — agentic retrieval

```bash
# routing: how much retrieval does this question deserve?
.venv/bin/python scripts/ask.py --mode route "what python version do we target"
.venv/bin/python scripts/ask.py --mode route "which services use the v3 auth flow, and who owns them?"

# retrieve -> grade -> re-query, bounded at 3 attempts
.venv/bin/python scripts/ask.py --mode agentic "why is it 502ing?"
```

Watch the attempt log. The rank-32 document is usually found on attempt 2, because the
grader says what was missing and the loop searches for exactly that.

### Section 07 — production

```bash
# permission-aware retrieval: the same question, two callers
.venv/bin/python scripts/ask.py --mode result "what did the Q2 penetration test find?"
.venv/bin/python scripts/ask.py --mode result "what did the Q2 penetration test find?" --as security-team

# the offline gate
.venv/bin/python scripts/bench.py --modes naive query result --top-k 5 --min-recall 0.75
```

---

## The numbers

Measured on a laptop RTX 4060, 41 documents / 120 chunks, the 25-question golden set.
Reproduce with `scripts/bench.py`.

| Mode | recall@5 | recall@8 | Median | p95 |
|---|---|---|---|---|
| `naive` | 0.76 | 0.84 | 0.12 s | 0.13 s |
| `query` | 0.80 | 0.88 | 1.86 s | 2.39 s |
| `result` | 0.72–0.76 | 0.88 | 3.91 s | 4.38 s |
| `agentic` | 0.84 | 0.88 | 5.89 s | 15.05 s |

Only `naive` gives the same result every time. Every other mode has an LLM in its path
and varies by about ±0.04 between runs. That's why the lecture reports ranges.

Where the cut costs you:

| Stage | recall@5 |
|---|---|
| Fused candidate set, top 16 | **0.92** |
| Cut to 5 by fusion score | 0.68 |
| Cut to 5 by the LLM reranker | 0.76–0.80 |

Where the latency is:

| Stage | Median |
|---|---|
| Embed the query | 104 ms |
| **pgvector search, k=16** | **3 ms** |
| Self-query extraction | 648 ms |
| Multi-query expansion | 603 ms |
| Rerank 16 (4-way concurrent) | 2,004 ms |
| Generate the grounded answer | 3,535 ms |

---

## Things that did not work

Kept on purpose, because the negative results are the most useful part of the project.

| Technique | Measured | Why |
|---|---|---|
| Contextual retrieval | naive 0.76 → **0.72** | Its precondition didn't hold — the chunks already described themselves, so the generated prefix added noise |
| Titles in the reranker prompt | 0.80 → **0.76** | Reverted. An idea that sounds good isn't an improvement until it's measured |
| Batched JSON reranking | All-zero score arrays | Wiped out the fused order. One passage per call is more reliable and runs in parallel |
| Hard metadata filters from self-query | 0.76 → **0.52** | The model made up `doc_type: postmortem` for a runbook question, which removed the answer completely |
| `num_predict` to cap a reasoning model | Empty outputs | The thinking used up the limit before any answer was written |

> **41 documents is too small a corpus to show what these techniques do at scale.** With
> 120 chunks, a decent embedding model finds most things by itself. That's why reranking
> underdelivered here. At 100,000 chunks, the sheer number of near-misses is what makes
> two-stage retrieval essential. *"It worked on my forty-document demo"* is how bad RAG ends
> up in production.

---

## Layout

```
corpus/                  41 documents with YAML frontmatter (service, doc_type, version,
                         status, visibility, updated_at)
golden_set.json          25 questions, each labelled with the failure mode it exercises
docs_assistant/
  settings.py            env config
  ollama_client.py       embed / complete / chat_with_tools
  db.py                  schema, connection, vector literals
  ingest.py              parse -> chunk -> contextualise -> embed -> write
  generate.py            the grounding contract                      §03
  pipeline.py            the three fixed pipelines                   §03-05
  agent_minimal.py       the 15-line loop                            §01
  agent.py               the hardened loop + four tools              §02
  cache.py               embedding + retrieval caches                §07
  retrieve/
    naive.py             embed -> top-k                              §03
    query_side.py        rewrite / expand / HyDE / self-query        §04
    result_side.py       RRF / rerank / MMR / parent / reorder       §05
    agentic.py           grade -> re-query, and routing              §06
scripts/
  seed.py                corpus -> pgvector
  ask.py                 --mode none|naive|query|result|agentic|agent|minimal|route
  bench.py               recall@k + latency; --min-recall gates CI
  trace_agent.py         per-iteration token accounting              §01
```

The corpus has retrieval traps built in on purpose: a root-cause ADR that never contains
the string "502", a superseded runbook with almost the same title as the active one, an
ownership answer that lives in another service's document, a restricted postmortem, a
draft ADR that must not be reported as decided, and a multi-hop question whose two halves
are in two separate tables.

---

## Homework

See `../Homework.md`. In short: run this project locally, pick two questions from
`golden_set.json`, ask each in `naive`, `query`, `result` and `agentic`, and publish the
answers as a Gist whose link goes into the feedback form. Trying other models or providers
is appreciated.

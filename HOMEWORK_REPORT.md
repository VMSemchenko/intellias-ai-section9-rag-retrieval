# Section 9 homework: four retrieval modes on two golden-set questions

**Course:** Intellias NextGen Engineering Program, AI Product Engineer, *Agents, RAG Fundamentals & Advanced Retrieval*
**Author:** Vadym Semchenko, 8 November 2026
**Task:** run two `golden_set.json` questions through `naive`, `query`, `result` and `agentic`, then compare the retrieved context and the answers.

---

## Summary

| | Q1 `q-502-vague`: *"why is it 502ing?"* | Q2 `q-v3-consumers-owners`: *"which services still use the deprecated v3 auth flow, and who owns them?"* |
|---|---|---|
| Failure mode | vocabulary mismatch: the cause (`adr-0061`) never says "502" | multi-hop: register table + ownership table (`match: all`) |
| **naive** | ✗ symptom-level triage only. `adr-0061` best chunk is rank **22/120** | ✓ honest refusal: has the table's lead-in sentence, not the table |
| **query** | ✗ same as naive, with expansions that drift to "gateway timeout" (504) | ✓ honest refusal (identical top 5 to naive) |
| **result** | ✓ **correct root cause**, reached via the postmortem and runbook, *not* `adr-0061` | ◐ 4 services + team names, then a contradictory "I don't have that" |
| **agentic** | ✓ **only mode that retrieves `adr-0061`** (attempt 2), but it missed in the benchmark re-run. Answer has no inline citations | ◐ 4 services + team names, cited. Grader says "sufficient" on attempt 1 |
| Expected docs in top 5 | only agentic, 1 run in 2 | **no mode** retrieves `policy-service-ownership` |
| Full golden set, recall@5 | naive **0.80** · query **0.84** · result **0.68** · agentic **0.80** | median retrieval latency 0.03 s · 1.5 s · 10.8 s · 25.2 s |

Five findings matter more than the per-mode verdicts:

1. **Result mode reranks only the first 16 of ~24 fused chunks, and both questions' expected documents fall past that cut.** `adr-0061` sat at fused ranks 19 and 21 (Q1). The register table `policy-deprecation#1` and `policy-service-ownership` sat at fused ranks 17 and 18 (Q2). The reranker never saw any of them.
2. **Parent expansion (±1 chunk) carries Q2 and most of Q1.** The register table is chunk `#1`, but only `#0` (which ends with *"Services still calling … as of the last audit:"*) ever ranks. Naive and query refuse because of this boundary; result and agentic answer because the window pulls `#1` in.
3. **Agentic's wins come from eval leakage, and they aren't reliable.** The grader prompt's few-shot examples include this exact question and the rescue query `"outbound connection pool saturation upstream timeout"`. Attempt 2 used that string verbatim. Even so, agentic missed `q-502-vague` in the full benchmark run. Its only net gain over naive across the golden set is `q-page-catalog`, which mirrors the grader's other example ("who owns catalog?"). The self-query and router prompts also contain `"why is it 502ing?"`.
4. **Soft self-query filters are a real safeguard, and I can show it in this run.** Q3's extracted `doc_type: policy` + `service: auth-svc` matches **0 documents**, and Q2's `service: auth-svc, version: v3` matches only the two *superseded* docs. As hard SQL `WHERE` filters, both would have destroyed recall. As an extra ranked list, they cost one query each.
5. **Model swap (bonus): `mistral:latest` copied the grounding prompt's example answer** ("Thumbnails stop appearing when the resize queue backs up…") into **6 of 8** answers, with citations to documents that don't exist. On qwen2.5 this never happened.

---

## Setup

| | |
|---|---|
| Hardware | Apple M2 Pro, 16 GB RAM, macOS 26.7.1 |
| Runtime | Ollama 0.40.15, Postgres 17 + pgvector 0.8.7 (Docker, port 5434), Python 3.13 |
| Embeddings | `embeddinggemma:300m` (768-d), 41 documents → 120 chunks, no contextual prefixes |
| Chat / rerank / grader model | `qwen2.5:7b-instruct` (main runs), `mistral:latest` (bonus comparison) |
| Command | `scripts/ask.py --mode <mode> "<question>" --show-context`, one run per cell, models warmed up first |

Raw outputs for every run are in [`results/`](results/). `results/stage_trace.txt` is an instrumented re-run of the result-mode stages: fused rank → rerank score → MMR. Each cell is a single run. Expansions (temperature 0.4) and rerank scores vary between runs, so treat individual numbers as one sample. The structural findings (chunk boundaries, rerank cut, prompt contents) are deterministic.

## What each mode does (from the code)

| Mode | Pipeline | LLM calls per question in this run |
|---|---|---|
| `naive` | embed question → top 5 by cosine distance | **1** (answer only) |
| `query` | self-query filter extraction → 2 multi-query expansions → one ranked list per query, plus one *filtered* list per query when filters exist → union, dedupe by best distance | **3** |
| `result` | `query` stages at depth 16 → RRF → pointwise LLM rerank of the **top 16** (0–10 scale) → top 10 → MMR (λ = 0.7) to 5 → parent expansion (±1 chunk) → reorder for attention (best first, second-best last) | **19** (2 + 16 rerank + answer) |
| `agentic` | `result` pipeline → LLM grader decides "sufficient?" → if thin, retries with the grader's `next_query` (max 3 attempts) → merge by rerank score | **20** (Q2, 1 attempt) / **39** (Q1, 2 attempts) |

Every mode shares the same generation step: a grounding contract that requires `[doc-id#ordinal]` citations, prefers `active` over `superseded`, and gives an exact refusal phrase.

---

## Q1: "why is it 502ing?" (`q-502-vague`, expected `adr-0061`)

The question has no service, no version and a pronoun subject. The root cause is `adr-0061`: checkout's `httpx` connection pool kept the library default of 10 connections after the v4 token exchange added one outbound call per token lifetime. The pool saturated, requests failed with `PoolTimeout`, and the edge turned that into a 502 with nothing in checkout's own logs. The ADR never contains "502".

### Retrieved top 5

| # | naive (d) | query (d) | result (d · rerank) | agentic (d · rerank) |
|---|---|---|---|---|
| 1 | `adr-0019#1` .465 | `rb-gateway-timeouts#0` .457 | `rb-checkout-502#0` .465 · 9 | **`adr-0061#2`** .459 · 9 |
| 2 | `rb-checkout-502#0` .465 | `adr-0019#1` .465 | `adr-0019#1` .465 · 9 | `adr-0019#1` .465 · 9 |
| 3 | `rb-gateway-timeouts#1` .490 | `rb-checkout-502#0` .465 | `pm-2026-07-checkout-latency#0` .595 · 6 | `rb-checkout-502#0` .465 · 9 |
| 4 | `rb-gateway-timeouts#0` .543 | `rb-gateway-timeouts#1` .490 | `pm-2026-07-checkout-latency#1` .587 · 9 | `rb-checkout-502#1` .489 · 9 |
| 5 | `rb-gateway-timeouts#2` .582 | `rb-checkout-502#2` .494 | `pm-2026-07-checkout-latency#2` .611 · 9 | `pm-2026-07-checkout-latency#1` .587 · 9 |
| Chunks considered | 5 | 9 | 24 | 24 per attempt |
| End-to-end time | 10.6 s | 10.7 s | 24.0 s | 40.8 s |

All retrieved chunks are `active`. Result-mode rows appear in attention order: the rerank-6 chunk is deliberately buried at position 3.

### Query-side trace

- **query:** filters `{}`, which is correct: the self-query prompt lists this exact question as returning `{}`. No rewrite, because there is no history. Expansions: *"why are we getting bad gateway errors?"* and *"why is the service returning gateway timeout?"*. The second one drifted from 502 to 504, a different failure with a different owner per `rb-gateway-timeouts`.
- **result:** expansions *"…bad gateway errors?"* and *"…returning an upstream 502?"*. 24 fused chunks. The stage trace shows `adr-0061#0` and `#1` at **fused ranks 19 and 21**, past the 16-chunk rerank cut. Four chunks scored 9: `rb-checkout-502#0`, `adr-0019#1`, `pm-2026-07#1` and `#2`.
- **agentic:** attempt 1 = the result pipeline on the raw question → *"thin — missing the root cause"*. Attempt 2 = `'outbound connection pool saturation upstream timeout'` → *sufficient*. `adr-0061#2` now ranks first.

### Answers

| Mode | Answer (abridged) | Assessment |
|---|---|---|
| naive | "may 502 due to a connection that never reached a handler… `upstream_status` `-` or `0`… connection refusal, reset… or the upstream itself returning 502" | Grounded and cited, but it explains *what a 502 is*, not *why this one happens* |
| query | Same triage, with advice to check `upstream_status` | Same: no cause |
| result | "outbound connection pool in `checkout-svc` saturated under load after the v4 auth migration… default `httpx` pool size of 10… requests failing to acquire a connection… `502 Bad Gateway`" | **Correct root cause.** It cites only `[rb-checkout-502#0]`, but the "10 connections" detail comes from the postmortem chunks, which go uncited |
| agentic | "outbound connection pool… saturated, leading to `PoolTimeout`… not retried, as per… ADR-0061… I don't have that in the docs. To find the exact configuration…" | Correct cause plus the no-retry rule. **But no `[doc#n]` citations** (breaks rule 2), and the refusal phrase is stuck onto a real answer |

**Why result mode gets the cause without `adr-0061`:** the ±1 parent window around `rb-checkout-502#0` includes `#1`, whose step 2 reads *"Check the outbound pool before anything else. This is the most common cause since the v4 migration… `PoolTimeout`… ADR-0061"*. The postmortem (best chunk rank 6/120, so easy to retrieve) tells the same story. Here the corpus has redundancy that saves the pipeline. With only the ADR, result mode would have failed like naive.

**Why agentic finds `adr-0061`, and why that's partly a test artifact:** `GRADE_SYSTEM` in `docs_assistant/retrieve/agentic.py` contains, as a few-shot example:

```
Q: "why is it 502ing?"
Passages list 502 triage steps but never say what causes it.
-> {"sufficient": false, "missing": "the root cause",
    "next_query": "outbound connection pool saturation upstream timeout"}
```

The grader returned exactly that `next_query`. The mechanism (grade → name what's missing → re-query) is sound, but this golden question can't measure it fairly while its answer path sits in the prompt. The same question also appears in `SELF_QUERY_SYSTEM` and `ROUTE_SYSTEM`. The bonus run below shows what happens without that crutch: mistral's grader wrote its own re-queries and never found `adr-0061`.

---

## Q2: "which services still use the deprecated v3 auth flow, and who owns them?" (`q-v3-consumers-owners`, expected `policy-deprecation` **and** `policy-service-ownership`)

The first hop is the register table in `policy-deprecation`: catalog-svc / Discovery, notify-svc / Messaging, ledger-svc / Money, admin-console / Internal Tools. That same doc says its team names are *informal* and that the authoritative owner, on-call rota and escalation contact are in `policy-service-ownership`, the second hop. That doc holds the tech leads (e.g. catalog-svc → Iryna Palamar, `#team-discovery`).

### Retrieved top 5

| # | naive (d · status) | query (d · status) | result (d · rerank · status) | agentic (d · rerank · status) |
|---|---|---|---|---|
| 1 | `api-auth-v3#0` .432 **sup** | `api-auth-v3#0` .433 **sup** | `adr-0031#1` .509 · 9 **sup** | `adr-0031#1` .509 · 9 **sup** |
| 2 | `policy-deprecation#0` .452 | `policy-deprecation#0` .448 | `adr-0031#0` .485 · 6 **sup** | `policy-deprecation#0` .448 · 6 |
| 3 | `adr-0031#0` .493 **sup** | `adr-0031#0` .476 **sup** | `api-auth-v4#0` .571 · **0** | `adr-0031#0` .485 · 6 **sup** |
| 4 | `adr-0031#1` .513 **sup** | `adr-0031#1` .504 **sup** | `rb-platform-secret-rotation#0` .550 · **0** | `api-auth-v4#0` .571 · **0** |
| 5 | `adr-0042#2` .523 | `adr-0042#2` .519 | `policy-deprecation#0` .448 · 6 | `pm-2026-04-auth-outage#0` .607 · **0** |
| Chunks considered | 5 | 6 (from 6 lists!) | 23 | 23 |
| End-to-end time | 5.2 s | 4.2 s | 26.2 s | 20.3 s |

`sup` = `status: superseded`. In naive, three of the five chunks are superseded.

### Query-side trace

- **query / result filters:** `{'service': 'auth-svc', 'version': 'v3'}`. That filter matches only `adr-0031` and `api-auth-v3`, both superseded. The answer lives in `policy-deprecation` (`service: platform`). As a hard filter it would have hidden the answer completely; as an extra list it's harmless. Query mode ran 6 ranked lists, yet they produced only **6 distinct chunks**: the two expansions (*"…outdated v3 authentication process…"*, *"…obsolete v3 authorization mechanism…"*) are paraphrases that land in the same neighbourhood, so multi-query added no diversity.
- **result:** the stage trace puts the register table `policy-deprecation#1` at **fused rank 17** and `policy-service-ownership#2` at **fused rank 18**, just past the rerank cut. In that trace the reranker scored 13 of the 16 chunks it saw as **0**. In the main run, too few chunks scored above zero, so MMR had to fill two of five slots with rerank-0 chunks (`api-auth-v4#0`, `rb-platform-secret-rotation#0`).
- **agentic:** attempt 1 → *sufficient*. The grader accepted the register's "Owner team" column as the ownership answer and stopped. Its own few-shot example (*"who owns catalog?" → "service ownership table escalation contacts"*) is exactly the second hop it skipped.

### Answers

| Mode | Answer (abridged) | Assessment |
|---|---|---|
| naive | "I don't have that in the docs. To find this information, you would need: the list of services that still call `POST /v3/session/introspect`." | **Correct refusal.** `policy-deprecation#0` ends with that sentence, and the table starts in `#1` (rank 7/120) |
| query | Identical refusal | Same: query-side fixes don't help when the right *document* is found but the wrong *chunk* is |
| result | "catalog-svc: Discovery; notify-svc: Messaging; ledger-svc: Money; admin-console: Internal Tools… I don't have that in the docs. I would need the current status of `checkout-svc` and `gateway`" | First hop correct. The tail contradicts the context: the expanded table says both "completed migration in July 2026". No inline citations |
| agentic | Same four services and teams, "listed in the current deprecation register [policy-deprecation#0]" | Cleanest answer. Second hop still missing: informal team names only, no authoritative owner or escalation contact |

**Verdict:** under the golden set's `match: all`, all four modes fail. Naive and query fail *safely*: they refuse and name the missing item. Result and agentic give a useful partial answer. Neither has the mechanism this question needs: a second lookup that depends on the first (decompose → look up services → look up their owners). `query_side.decompose()` exists in the codebase but no pipeline calls it.

---

## Across the whole golden set (`scripts/bench.py`, top-k 5)

To check whether the two-question picture holds, I ran the whole 25-question golden set once per mode. This is retrieval only, with no answer generation ([`results/bench_qwen.json`](results/bench_qwen.json)).

| Mode | recall@5 (mine, M2 Pro) | recall@5 (README, RTX 4060) | Median (mine / README) | p95 (mine / README) |
|---|---|---|---|---|
| `naive` | 0.80 | 0.76 | 0.03 s / 0.12 s | 0.05 s / 0.13 s |
| `query` | **0.84** | 0.80 | 1.51 s / 1.86 s | 2.40 s / 2.39 s |
| `result` | **0.68** | 0.72–0.76 | 10.77 s / 3.91 s | 13.45 s / 4.38 s |
| `agentic` | 0.80 | 0.84 | 25.21 s / 5.89 s | 41.07 s / 15.05 s |

With 25 questions, one question is worth 0.04, and the README reports about ±0.04 run-to-run variance for every mode that has an LLM in it. Treat differences of one question as noise. Part of this run overlapped with other CPU-heavy work on the machine, so my LLM-mode latencies are pessimistic; recall isn't affected by load. The 3–4× latency gap to the README's numbers is mostly Apple-silicon versus RTX-4060 inference for 16 rerank calls per attempt.

**Which questions each mode missed:**

| Question (expected doc) | naive | query | result | agentic |
|---|---|---|---|---|
| `q-502-vague` (`adr-0061`) | ✗ | ✗ | ✗ | ✗ |
| `q-502-dashboards` (`adr-0061`) | ✗ | ✗ | ✗ | ✗ |
| `q-v3-consumers-owners` (2 docs, `all`) | ✗ | ✗ | ✗ | ✗ (1 of 2 found, rank 2) |
| `q-provider-mismatch` (`adr-0067`) | ✗ | ✓ | ✗ | ✗ |
| `q-page-catalog` (`policy-service-ownership`) | ✗ | ✓ | ✗ | ✓ |
| `q-partner-disable` (`api-notify-webhooks`) | ✓ | ✗ | ✗ | ✗ |
| `q-upstream-status` (`adr-0019`) | ✓ | ✓ | ✗ | ✓ |
| `q-skip-rotation-wait` (`rb-auth-token-rotation`) | ✓ | ✓ | ✗ | ✓ |
| All other 17 questions | ✓ | ✓ | ✓ | ✓ |

What this adds to the two deep dives:

- **More stages didn't mean more recall.** Result mode missed every question naive missed, plus three naive answers (`q-upstream-status`, `q-skip-rotation-wait`, `q-partner-disable`). That's three questions, outside the noise band. Result mode loses documents at two cuts. The README's own stage table shows the fused top 16 still holds recall **0.92**, so most of the loss happens when rerank + MMR cut that pool to 5. My stage trace shows a second, earlier cut: the featured questions' documents sit past fused rank 16, so the reranker never sees them at all.
- **Agentic's Q1 success isn't reproducible.** In this run, agentic *missed* `q-502-vague` (13.2 s, so it most likely stopped after one attempt), even with its rescue query sitting in the prompt. That's 1 hit in 2 runs.
- **Agentic's one net gain over naive is the other few-shot question.** It found `q-page-catalog` ("who do I page for catalog") at rank 1, after 41 s. The grader prompt's second example is `"who owns catalog?" → next_query "service ownership table escalation contacts"`. So both golden questions that agentic should win on have their answer paths in its prompt, and it reliably won only one of them.
- **Query mode was the best recall-per-second** in this run (0.84 at 1.5 s). The vocabulary-mismatch family (`q-502-*`) beat every mode.

---

## Bonus: same questions with `mistral:latest`

`CHAT_MODEL=mistral:latest` changes the filter, expansion, rerank, grader and answer model. Embeddings stay the same, so naive retrieval is identical.

| Mode | Q1 time | Q1 outcome | Q2 time | Q2 outcome |
|---|---|---|---|---|
| naive | 15.0 s | **template leak** + generic triage | 8.0 s | honest refusal, cited |
| query | 13.2 s | triage + a stray "you would need the service name…" | 16.4 s | **template leak**; retrieved the table (`policy-deprecation#1`) but described the policy instead |
| result | 31.6 s | **template leak** + "This issue is related to the media service" (invented) | 31.5 s | **template leak** + only `catalog-svc / Discovery` (1 of 4) |
| agentic | 72.9 s | 3 attempts, ceiling hit, never found `adr-0061`; answer = template leak only | 74.9 s | sufficient on attempt 3; **template leak** + 1 of 4 services |

- **Template leakage, 6 of 8 answers.** The grounding contract includes an example answer about a non-existent media service, marked "match its shape, never its content". Mistral reproduced it verbatim, citations included (`[rb-media-thumbnails#0]`, `[adr-0090#2]`), and none of those documents exist. Qwen2.5 never did this in 12 runs. A post-generation check that every cited id was in the retrieved set would catch it for free.
- **Better retrieval, worse answers.** Mistral's self-query moved "v3" into the filter and dropped it from `semantic_query`. That unfiltered phrasing brought the register table `policy-deprecation#1` into the top 5 (query) and to rerank 9 at rank 1 (result), which qwen never achieved. Mistral then failed to read the table.
- **Grader without the crutch.** Mistral's Q1 re-queries were its own: `'cause of 502 errors in the context of edge routing… (adr-0019#1)'`, then `'postmortem or runbook related to checkout service…'`. They included a literal citation token and never reached `adr-0061`. It ran 3 attempts for **72.9 s**.
- Mistral was 1.2–3.9× slower end to end. The agentic rows aren't like-for-like: mistral needed 3 attempts where qwen needed 1–2.

The lesson matches what the README says about reasoning models: every stage of this pipeline is a small LLM task, so the model choice changes behaviour at *every* stage, not just answer quality.

---

## Engineering observations

**naive.** Retrieval is deterministic and cheap (one embedding; most of the ~5 s end-to-end time is answer generation). It works when the question uses the document's vocabulary and fails on the two things these questions test: vocabulary mismatch (Q1) and answers that start in one chunk and continue in the next (Q2). Its failure on Q2 is the *good* kind: the grounding contract made it refuse instead of guessing.

**query.** Expansion helps vocabulary mismatch only if the paraphrases reach the cause's vocabulary. On Q1 they stayed in symptom language ("bad gateway", even "gateway timeout"); on Q2 they were near-duplicates. The main value of this stage was **safety**: in this run alone, two hallucinated or over-specific filters would have zeroed recall as hard `WHERE` clauses (Q3: `auth-svc`+`policy` → 0 docs; Q2: `auth-svc`+`v3` → only superseded docs). Running them as an extra ranked list made them harmless.

**result.** Each stage has a visible effect, but they don't all pull their weight:
- *Parent expansion* did the most work: it fixed both chunk-boundary problems.
- *Rerank depth* was the bottleneck: the fused pool (23–24) is larger than the reranked slice (16), and the decisive chunks sat at 17–21. Reranking the whole pool costs ~8 more short LLM calls and would have shown the reranker `adr-0061` and the register table.
- *MMR* didn't stop same-document redundancy: Q1's final five included three chunks of one postmortem. With parent expansion on top, the same paragraphs went to the model up to three times. Merging overlapping windows per document before generation would shrink the context.
- *Citations get coarser after expansion:* `[rb-checkout-502#0]` really cites the window #0–#1, so an ordinal no longer points at the sentence that supports the claim.
- *Cost:* 19 LLM calls and ~24 s end-to-end versus 1 call / ~5 s for naive.

**agentic.** grade → name the gap → re-query is the right shape, and on Q1 it was the only mode to retrieve the answer document. Three caveats from these runs. First, both golden questions where it beats naive (`q-502-vague`, `q-page-catalog`) have their answer paths in the grader's few-shot examples, so its score overstates the method. Second, even with that help, it found `adr-0061` in only 1 of 2 runs. Third, the grader is lenient by design ("even a partial one… does not have to be complete") and accepted Q2 after one hop. It costs 1–3× the result pipeline (20–39 LLM calls, 20–41 s here; mistral hit 73–75 s). It should sit behind `route` mode rather than run on every question. In this run, `route` sent Q1 → `full`, Q2 → `agentic` and Q3 → `one_shot`. That split is sensible, and naive alone did answer Q3 correctly. But Q1 and Q2 are also the router's few-shot examples, so this doesn't show how it routes unseen questions ([`results/route.txt`](results/route.txt)).

**generation (all modes).** qwen2.5 followed the contract well (cited, preferred `active` over `superseded`; Q3 below shows all four modes resolving the v3/v4 conflict correctly). It had two recurring failures: the exact refusal phrase gets stuck onto a correct answer (Q1 agentic, Q2 result), and sometimes the inline citations are dropped entirely (Q1 agentic).

## What I'd change, in order of value per effort

1. **Rerank the full fused pool** (`fused[:len(fused)]`, or depth ≥ 24). This is a one-line change, at the cost of ~8 more short LLM calls, and it would have put `adr-0061` and the register table in front of the reranker in both questions. I haven't tested whether they'd then survive rerank + MMR.
2. **Remove golden-set questions from the few-shot examples** in `GRADE_SYSTEM`, `SELF_QUERY_SYSTEM` and `ROUTE_SYSTEM`, or exclude those questions from the score. Otherwise bench numbers for the agentic and query modes are inflated.
3. **Validate citations after generation:** every `[doc#n]` must be in the retrieved set, and a sentence-level check is a stretch goal. This would have caught all of mistral's fabricated citations.
4. **Wire `decompose()` into the agentic path** for questions the router classifies as `agentic`, so the second lookup is driven by the first ("who owns catalog-svc, notify-svc, ledger-svc, admin-console").
5. **Merge overlapping parent windows per document** and make MMR penalise same-doc picks, so the five slots are five sources.
6. **Chunk tables with their lead-in sentence.** `policy-deprecation` splits *"Services still calling … as of the last audit:"* from the table it introduces, and that boundary alone caused the naive/query refusal.

---

## Appendix A: Q3 `q-auth-every-request`, the superseded-conflict question

*"do we still need to call auth on every request"* (expected `adr-0042`). All four modes answered correctly: **No**. ADR-0042 (active, supersedes ADR-0031) has services verify short-lived tokens locally against the JWKS. This held even though the superseded `api-auth-v3#0` is the nearest chunk overall (rank 1/120) and lexically says "yes". The status field in each context header, plus contract rule 4 ("prefer active over superseded"), was enough even for naive. Times: naive 5.2 s, query 6.8 s, result 22.7 s, agentic 16.4 s (sufficient on attempt 1). Query mode extracted the hallucinated `doc_type: policy` filter discussed above, with no effect on the result. I left this question out of the main comparison because it doesn't separate the modes.

## Appendix B: reproduce

```bash
ollama pull embeddinggemma:300m && ollama pull qwen2.5:7b-instruct
docker compose up -d
python3 -m venv .venv && .venv/bin/pip install -e . && cp .env.example .env
.venv/bin/python scripts/seed.py --reset          # 41 documents / 120 chunks

for mode in naive query result agentic; do
  .venv/bin/python scripts/ask.py --mode $mode "why is it 502ing?" --show-context
  .venv/bin/python scripts/ask.py --mode $mode "which services still use the deprecated v3 auth flow, and who owns them?" --show-context
done

CHAT_MODEL=mistral:latest .venv/bin/python scripts/ask.py --mode result "why is it 502ing?"   # bonus
.venv/bin/python scripts/bench.py --modes naive query result agentic --top-k 5
```

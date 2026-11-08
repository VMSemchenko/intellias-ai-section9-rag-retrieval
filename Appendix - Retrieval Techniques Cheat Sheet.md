# Appendix — Retrieval Techniques Cheat Sheet

> Reference material, not a lecture section. One table to take back to your own corpus,
> plus the order to adopt things in and the numbers this lecture actually measured.

---

## Symptom → Technique

Start from the symptom, not the technique. Each row shows where it runs and what it costs.
A dash in *Deck slide* means the technique was cut from the live deck to keep it to 40
slides; it's covered in its section note and in *Not in the Live Deck* below.

| Symptom you can observe | Technique | Runs at | Cost per query | Section | Deck slide |
|---|---|---|---|---|---|
| Follow-up questions retrieve nonsense | Query rewriting | query | 1 LLM call (~0.5 s) | §04 | 28 |
| Answers use different words than questions | Multi-query expansion | query | 1 call + N searches (~0.7 s) | §04 | 28 |
| Questions are short, answers are long prose | HyDE | query | 1 call (~1.0 s) | §04 | — |
| One question, two independent parts | Decomposition | query | 1 call + N searches | §04 | — |
| Question assumes a mechanism it doesn't name | Step-back prompting | query | 1 call (~0.4 s) | §04 | — |
| Corpus has versions / services / doc types | **Self-query filters** | query | 1 call (~0.6 s) | §04 | 29 |
| **recall@50 ≫ recall@5** | **Retrieve wide + rerank** | query | 1 call per candidate | §05 | 30–32 |
| Several ranked lists to merge | RRF | query | **free** | §05 | 28 (callout) |
| Top-5 is three chunks of one document | MMR | query | free (needs stored vectors) | §05 | — |
| Right chunk, can't answer on its own | Parent expansion | query | 1 extra SQL query | §05 | 33 |
| Chunks meaningless without their heading | Contextual retrieval | **ingest** | 1 call per chunk, **offline** | §05 | 38 (callout) |
| Long context, answer in the middle is ignored | Reorder for attention | query | **free** | §05 | — |
| Really out of context space | Contextual compression | query | 1 call per candidate | §05 | — |
| Cheap questions paying expensive-path latency | **Routing** | query | 1 call (~0.4 s) | §06 | 36 |
| Retrieval sometimes silently returns nothing useful | Grade → re-query loop | query | 1 call per attempt | §06 | 35 |
| Multi-hop lookups that depend on each other | Agentic retrieval | query | N iterations, unbounded p95 | §06 | 34 |
| Answers cite documents that no longer exist | Content-hash re-index + delete pass | ingest | ~free | §07 | 43 |
| Two documents disagree | Recency/status ranking penalty | query | free (SQL) | §07 | 43 |
| Same query embedded repeatedly | Embedding cache | query | free after first hit | §07 | 43 |
| A user sees a document they should not | **ACL predicate in the `WHERE`** | query | free | §07 | 42 |

---

## Adoption Order

If you're starting from a naive `embed → search → generate` pipeline, do these in order.
Each step is cheap, and each one tells you whether the next one is worth doing.

1. **Build a golden set of 20–30 questions.** Write them from the *symptom*, never from the
   answer document. Without this, everything below is guesswork. (§07)
2. **Measure recall at a wide k**: 5, 20, 50. This one measurement tells you which half of
   your system is broken. (§05)
3. **Add the grounding contract**: only from context, cite every sentence, a clear way to
   say "I don't know", plus one example of the right answer shape. It's the cheapest
   quality win there is, and it costs nothing per query. (§03)
4. **Metadata in the context header**: `status`, `updated_at`, `doc_id`. This lets the
   model reason about conflicting and outdated sources. (§03, §07)
5. **Permission filter in the `WHERE` clause**, failing closed. Do it before it becomes a
   problem, not after. (§07)
6. If recall@50 ≫ recall@5: **retrieve wide and rerank** with a purpose-built
   cross-encoder. In general, this is the most valuable structural change. (§05)
7. If users word things differently from the docs: **self-query filters** and
   **multi-query expansion**. Add them as *extra* ranked lists, so a bad extraction can't
   reduce recall. (§04)
8. **Reorder for attention** and **parent expansion**. Both are almost free. Do them once
   you're sending more than three passages. (§05)
9. **Routing.** Once the expensive path exists, stop paying for it on easy questions. (§06)
10. Only then: **agentic retrieval** for the remaining hard questions, with a hard limit on
    attempts. (§06)

Steps 1 and 2 aren't optional warm-up. They're what turns steps 6 and later into real
decisions instead of copying what others do.

---

## Not in the Live Deck — Self-Study

The live session keeps to the techniques that are most widely used in production. These
were cut from the deck, not from the lecture: each has a full write-up in its section note
and runs in `examples/`. Any of them is a good pick for the [[Homework]].

| Technique | One-line idea | Why it's not in the deck | Read |
|---|---|---|---|
| **HyDE** | Embed a made-up answer instead of the question, so the search runs in "answer space" | Off by default here: on internal service names it invents `payment-gateway-svc` for `checkout-svc`. Measure it before you adopt it | [[04 - Advanced Retrieval - Query-Side]] |
| **Decomposition** | Split a question into independent lookups and merge them | Only for *independent* parts; dependent parts need the re-query loop (slide 35) | [[04 - Advanced Retrieval - Query-Side]] |
| **Step-back prompting** | Retrieve for the more general question first, for background | Narrow use; one extra call | [[04 - Advanced Retrieval - Query-Side]] |
| **RRF, in full** | `Σ 1/(60 + rank)` across lists; the twelve-line implementation and the `Candidate` card | Summarised in one callout on slide 28; most used in hybrid search, which is the data foundations session | [[05 - Advanced Retrieval - Result-Side]] |
| **MMR** | Pick passages by relevance *minus* similarity to what's already picked | Didn't change recall here. Its lesson — read `rerank_score`, not cosine distance, after reranking — is in the note | [[05 - Advanced Retrieval - Result-Side]] |
| **Reorder for attention** | `[1,2,3,4,5] → [1,3,5,4,2]` — best passages at the edges of the context | Free, but matters less with modern long-context models | [[05 - Advanced Retrieval - Result-Side]] |
| **Contextual retrieval, in full** | LLM-written prefix per chunk before embedding | Made recall worse here (0.76 → 0.72); kept on slide 38 as the "measure first" lesson | [[05 - Advanced Retrieval - Result-Side]] |
| **Contextual compression** | Copy out the useful sentences verbatim before generating | Only worth it at 20+ passages | [[05 - Advanced Retrieval - Result-Side]] |
| **Grader before/after logs** | The six hard questions, before and after the grader fix | Compressed into one warning on slide 35 | [[06 - Agentic Retrieval]] |
| **Degradation policy** | Lower answer quality, never availability, when a stage fails | Overlaps the observability session | [[07 - Production Considerations]] |
| **Offline retrieval gate** | `bench.py --min-recall` fails the build | CI gates belong to the observability session | [[07 - Production Considerations]] |

---

## What This Lecture Measured

41 documents, 120 chunks, 25-question golden set, `embeddinggemma:300m` +
`qwen2.5:7b-instruct` on a laptop GPU. Reproduce with `python scripts/bench.py`.

### Pipeline comparison

| Mode | recall@5 | recall@8 | Median | p95 |
|---|---|---|---|---|
| `naive` | 0.76 | 0.84 | 0.12 s | 0.13 s |
| `query` | 0.80 | 0.88 | 1.86 s | 2.39 s |
| `result` | 0.72–0.76 | 0.88 | 3.91 s | 4.38 s |
| `agentic` | **0.84** | 0.88 | 5.89 s | **15.05 s** |

### Where the cut costs you

| Stage | recall@5 |
|---|---|
| Fused candidate set, top 16 | **0.92** |
| Cut to 5 by fusion score | 0.68 |
| Cut to 5 by LLM reranker | 0.76–0.80 |

### Latency by stage

| Stage | Median |
|---|---|
| Embed the query | 104 ms |
| **pgvector search, k=16** | **3 ms** |
| Self-query extraction | 648 ms |
| Multi-query expansion | 603 ms |
| RRF fusion | <1 ms |
| Rerank 16 (4-way concurrent) | 2,004 ms |
| Parent expansion | 7 ms |
| Generate grounded answer | 3,535 ms |

---

## Techniques That Did Not Work Here

These are written down because the negative results are more useful than the positive
ones, and because every one of them is widely recommended.

| Technique | Expected | Measured | Why |
|---|---|---|---|
| **Contextual retrieval** | ~35% fewer retrieval failures (published) | naive 0.76 → **0.72** | Its precondition didn't hold: the chunks were paragraph groups that already described themselves, so the generated prefix added noise, not missing context |
| **Titles in the reranker prompt** | Titles carry strong signal | 0.80 → **0.76** | Reverted. An idea that sounds good isn't an improvement until it's measured |
| **LLM as reranker** | The standard two-stage win | Recovered 0.68 → 0.80 on the cut, but no end-to-end gain over `query` | A general chat model was never trained to give consistent relevance scores. Use a purpose-built cross-encoder |
| **Batched JSON reranking** | Fewer calls, same signal | All-zero score arrays that wiped out the fused order | One passage, one number is far more reliable and runs in parallel |
| **Hard metadata filters from self-query** | Precision win | naive 0.76 → **0.52** | The model made up `doc_type: postmortem` for a runbook question, which removed the answer from the results completely |
| **`num_predict` to cap reasoning latency** | Bounded latency | Empty outputs | The thinking used up the limit, so the actual answer was never written |

> [!important] The transferable lesson
> Six widely recommended techniques, measured on one small corpus: two helped, one helped
> partly, and three made things worse. Published gains are hypotheses about *your* corpus.
> Each of these took minutes to test, and would have taken weeks to adopt on faith.

---

## Cost Model

Per query, counted in LLM calls, since that's what actually drives latency and cost.

| Mode | LLM calls | Composition |
|---|---|---|
| `naive` | 1 | generate |
| `query` | 3 | filters + expansion + generate |
| `result` | 3 + k | filters + expansion + **1 per candidate reranked** + generate |
| `agentic` | (3 + k + 1) × attempts | the above, plus a grader, per attempt |
| `agent` (tool loop) | 1 per iteration + the pipeline behind each `search_docs` | unbounded without a ceiling |

Because the reranker makes one call per candidate, `fetch_depth` is the most important
number in the config. Sixteen is a deliberate compromise: the recall ceiling at 16 was 0.92,
and going wider costs one more call for each extra candidate.

---

## Boundaries — Whose Session Covers What

| Topic | Covered in |
|---|---|
| Chunking strategies, embedding models, vector DB internals, hybrid search | *Data Foundations for AI Systems* |
| Multi-agent architectures, LangGraph/CrewAI, workflow orchestration | *Agentic Systems & Workflow Design* |
| Faithfulness/relevance scoring, eval frameworks, human-in-the-loop | *Evaluation, Testing & Quality of AI Outputs* |
| CI/CD, deployment, monitoring, tracing, TokenOps and cost control | *Observability, CI/CD & Production Workflows* |
| Guardrails, prompt injection, data leakage, OWASP LLM Top 10 | *Responsible AI & Safety, Security, OWASP* |
| LangChain basics, OpenAI/HF APIs, pandas/numpy | *Python for AI Engineering* |
| Foundation models, scaling laws, sampling, transformer intuition | Foundation-model sessions |

---

[[01 - Agent Fundamentals]] · [[Appendix - Local Setup with Ollama & pgvector]]

## Slides

Not a deck section. Print it, or attach it as a PDF handout next to the recording — it's
where every technique cut from the 40-slide deck lives, so share it even when the session
runs to time. If there's spare time in Q&A, the *Techniques That Did Not Work Here* table is
the one worth putting on screen.

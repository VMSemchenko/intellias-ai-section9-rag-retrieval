"""recall@k and latency per pipeline mode, over golden_set.json.

Deliberately minimal: it answers "did retrieval put the right document in front of the
model, and what did that cost". Scoring the generated answer for faithfulness and
relevance is the evaluation session's — this is the retrieval-side gate you run in CI.
"""

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from docs_assistant import pipeline  # noqa: E402
from docs_assistant.retrieve import agentic  # noqa: E402
from docs_assistant.settings import GOLDEN_SET_PATH  # noqa: E402

MODES = {
    "naive": lambda question, top_k: pipeline.retrieve_naive(question, top_k=top_k)[0],
    "query": lambda question, top_k: pipeline.retrieve_query_side(question, top_k=top_k)[0],
    "result": lambda question, top_k: pipeline.retrieve_result_side(question, top_k=top_k)[0],
    "agentic": lambda question, top_k: agentic.grade_and_requery(
        question, top_k=top_k
    ).candidates[:top_k],
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--modes", nargs="+", default=["naive", "query", "result"])
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--min-recall", type=float, default=0.0, help="fail the run below this")
    parser.add_argument("--json-out", type=Path, default=None)
    args = parser.parse_args()

    cases = json.loads(GOLDEN_SET_PATH.read_text())["cases"]
    if args.limit:
        cases = cases[: args.limit]

    report: dict[str, dict] = {}

    for mode in args.modes:
        retrieve = MODES[mode]
        found, latencies, misses = 0, [], []
        print(f"\n=== {mode} (top_k={args.top_k}, {len(cases)} cases) ===")

        for case in cases:
            started = time.monotonic()
            candidates = retrieve(case["question"], args.top_k)
            latencies.append(time.monotonic() - started)

            retrieved_docs = [candidate.doc_id for candidate in candidates]
            predicate = all if case.get("match") == "all" else any
            hit = predicate(doc_id in retrieved_docs for doc_id in case["expected_doc_ids"])
            found += hit
            rank = next(
                (
                    position
                    for position, doc_id in enumerate(retrieved_docs, start=1)
                    if doc_id in case["expected_doc_ids"]
                ),
                None,
            )
            if not hit:
                misses.append(case["id"])
            print(
                f"  {'HIT ' if hit else 'MISS'} rank={rank or '-':<3} "
                f"{latencies[-1]:5.1f}s  {case['id']:<10} {case['question'][:56]}"
            )

        recall = found / len(cases)
        report[mode] = {
            "recall_at_k": round(recall, 3),
            "median_latency_s": round(statistics.median(latencies), 2),
            "p95_latency_s": round(sorted(latencies)[max(0, int(len(latencies) * 0.95) - 1)], 2),
            "misses": misses,
        }
        print(
            f"  recall@{args.top_k}={recall:.2f}  "
            f"median={report[mode]['median_latency_s']}s  "
            f"p95={report[mode]['p95_latency_s']}s"
        )

    print("\n=== summary ===")
    print(f"{'mode':<10}{'recall@k':>10}{'median s':>10}{'p95 s':>8}")
    for mode, numbers in report.items():
        print(
            f"{mode:<10}{numbers['recall_at_k']:>10.2f}"
            f"{numbers['median_latency_s']:>10.2f}{numbers['p95_latency_s']:>8.2f}"
        )

    if args.json_out:
        args.json_out.write_text(json.dumps(report, indent=2))

    if args.min_recall:
        worst = min(numbers["recall_at_k"] for numbers in report.values())
        if worst < args.min_recall:
            print(f"\nFAIL: recall {worst:.2f} below threshold {args.min_recall:.2f}")
            sys.exit(1)


if __name__ == "__main__":
    main()

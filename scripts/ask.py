import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from docs_assistant import agent, agent_minimal, generate, pipeline  # noqa: E402
from docs_assistant.retrieve import agentic  # noqa: E402

MODES = ("none", "naive", "query", "result", "agentic", "agent", "minimal", "route")


def print_candidates(candidates, show_text: bool) -> None:
    if not candidates:
        print("  (nothing retrieved)")
        return
    for position, candidate in enumerate(candidates, start=1):
        score = (
            f" rerank={candidate.rerank_score:.0f}"
            if candidate.rerank_score is not None
            else ""
        )
        print(
            f"  {position}. [{candidate.cite()}] d={candidate.distance:.3f}{score} "
            f"{candidate.status:<10} {candidate.title[:58]}"
        )
        if show_text:
            print(f"       {candidate.context_text[:220].replace(chr(10), ' ')}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Ask the internal docs assistant.")
    parser.add_argument("question", nargs="+")
    parser.add_argument("--mode", choices=MODES, default="result")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--show-context", action="store_true")
    parser.add_argument(
        "--as",
        dest="visible_to",
        default=None,
        help="ACL group to retrieve as, e.g. security-team (section 07)",
    )
    args = parser.parse_args()
    question = " ".join(args.question)

    print(f"\nquestion: {question}\nmode:     {args.mode}\n")
    started = time.monotonic()

    if args.mode == "none":
        print(generate.answer_without_retrieval(question))

    elif args.mode == "minimal":
        print(agent_minimal.run(question))

    elif args.mode == "route":
        decision = agentic.route(question)
        print(f"route: {decision['route']}  ({decision['why']})")

    elif args.mode == "agent":
        run = agent.run(question, visible_to=args.visible_to)
        print("tool calls:")
        for step in run.steps:
            print(f"  {step.iteration}. {step.tool}({step.arguments}) -> {step.result_preview}")
        print(f"\nstopped: {run.stopped_because}")
        print(f"citations: {', '.join(run.citations) or 'none'}\n")
        print(run.answer)

    elif args.mode == "agentic":
        result = agentic.grade_and_requery(
            question, top_k=args.top_k, visible_to=args.visible_to
        )
        for number, attempt in enumerate(result.attempts, start=1):
            verdict = "sufficient" if attempt.sufficient else f"thin — missing {attempt.missing}"
            print(f"attempt {number}: {attempt.query!r}\n  -> {verdict}")
        print(f"\nstopped: {result.stopped_because}\nretrieved:")
        print_candidates(result.candidates[: args.top_k], args.show_context)
        print()
        print(generate.answer(question, result.candidates[: args.top_k]))

    else:
        retrieve = {
            "naive": pipeline.retrieve_naive,
            "query": pipeline.retrieve_query_side,
            "result": pipeline.retrieve_result_side,
        }[args.mode]
        kwargs = {"top_k": args.top_k}
        if args.mode != "naive":
            kwargs["visible_to"] = args.visible_to
        candidates, trace = retrieve(question, **kwargs)

        if trace.standalone_query != question:
            print(f"rewritten:  {trace.standalone_query}")
        if trace.filters:
            print(f"filters:    {trace.filters}")
        if len(trace.queries) > 1:
            for query in trace.queries[1:]:
                print(f"expansion:  {query}")
        if trace.candidates_considered:
            print(f"considered: {trace.candidates_considered} chunks")
        for note in trace.notes:
            print(f"note:       {note}")

        print("\nretrieved:")
        print_candidates(candidates, args.show_context)
        print()
        print(generate.answer(question, candidates))

    print(f"\n[{time.monotonic() - started:.1f}s]")


if __name__ == "__main__":
    main()

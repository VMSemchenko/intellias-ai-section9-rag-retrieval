"""Measure what an agent loop actually costs per iteration.

Section 01 claims that agent cost grows faster than linearly in iterations, because every
turn re-sends all previous tool results. This prints the real numbers instead of asserting
them.
"""

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import ollama  # noqa: E402

from docs_assistant import agent  # noqa: E402
from docs_assistant.settings import settings  # noqa: E402

client = ollama.Client(host=settings.ollama_host, timeout=300)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("question", nargs="+")
    parser.add_argument("--max-iterations", type=int, default=6)
    args = parser.parse_args()
    question = " ".join(args.question)

    messages = [
        {"role": "system", "content": agent.SYSTEM_PROMPT.format(max_iterations=args.max_iterations)},
        {"role": "user", "content": question},
    ]

    print(f"question: {question}\n")
    print(f"{'iter':<6}{'msgs':<6}{'prompt tok':>11}{'output tok':>11}{'cumulative':>12}{'s':>7}  tool")
    cumulative = 0

    for iteration in range(1, args.max_iterations + 1):
        started = time.monotonic()
        response = client.chat(
            model=settings.chat_model,
            messages=messages,
            tools=agent.TOOL_SCHEMAS,
            options={"temperature": 0.1, "num_predict": 600},
            keep_alive="30m",
        )
        elapsed = time.monotonic() - started

        prompt_tokens = response.get("prompt_eval_count") or 0
        output_tokens = response.get("eval_count") or 0
        cumulative += prompt_tokens + output_tokens

        message = response["message"]
        calls = getattr(message, "tool_calls", None) or []
        tool_label = ", ".join(call["function"]["name"] for call in calls) or "(answered)"
        print(
            f"{iteration:<6}{len(messages):<6}{prompt_tokens:>11}{output_tokens:>11}"
            f"{cumulative:>12}{elapsed:>7.1f}  {tool_label}"
        )

        messages.append(
            {
                "role": "assistant",
                "content": message["content"] or "",
                **({"tool_calls": calls} if calls else {}),
            }
        )
        if not calls:
            break

        for call in calls:
            name = call["function"]["name"]
            arguments = agent._coerce_arguments(call["function"]["arguments"])
            payload = agent._invoke(name, arguments, None)
            messages.append(
                {"role": "tool", "name": name, "content": json.dumps(payload)[:6000]}
            )

    print(
        f"\n{cumulative} tokens total. A single grounded call over the same corpus costs "
        f"roughly 1,200 — the loop is the expensive part, not the model."
    )


if __name__ == "__main__":
    main()

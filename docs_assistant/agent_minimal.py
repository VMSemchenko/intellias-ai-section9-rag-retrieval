"""The 15-line agent from lecture section 01.

Deliberately fragile: no iteration ceiling, no progress check, no context budget,
no tool-error handling. Section 02 fixes each of those. Run it with
`scripts/ask.py --mode minimal` and watch it misbehave.
"""

from . import ollama_client
from .retrieve.naive import search

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search",
            "description": "Search the docs.",
            "parameters": {
                "type": "object",
                "properties": {"q": {"type": "string"}},
                "required": ["q"],
            },
        },
    }
]


def run(question: str) -> str:
    messages = [{"role": "user", "content": question}]

    while True:
        response = ollama_client.chat_with_tools(messages, TOOLS)
        message = response["message"]
        messages.append(message)

        calls = message.get("tool_calls") or []
        if not calls:
            return message["content"]

        for call in calls:
            hits = search(call["function"]["arguments"]["q"])
            messages.append(
                {
                    "role": "tool",
                    "content": "\n".join(hit.text for hit in hits),
                }
            )

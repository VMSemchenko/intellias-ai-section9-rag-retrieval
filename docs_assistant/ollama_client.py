import ollama

from .settings import settings

_client = ollama.Client(host=settings.ollama_host, timeout=300)

KEEP_ALIVE = "30m"


def embed(texts: list[str]) -> list[list[float]]:
    response = _client.embed(model=settings.embedding_model, input=texts)
    return [list(vector) for vector in response["embeddings"]]


def embed_one(text: str) -> list[float]:
    return embed([text])[0]


def complete(
    system: str, user: str, temperature: float = 0.1, max_tokens: int = 400
) -> str:
    """`max_tokens` bounds the worst case; every call site knows roughly how long its own
    answer should be.

    A note on model choice, because it dominates the latency of this whole project: the
    chat model must be a NON-reasoning model. A reasoning model spends 1,000+ tokens
    deliberating before it emits the two-field JSON object a query rewriter needs, which
    turns a 0.6-second call into a 20-second one — and `num_predict` cannot save you,
    because the cap gets consumed by the reasoning and the actual answer comes back empty.
    Reasoning models earn their cost on hard single answers, not on the dozen small
    extraction and scoring calls a retrieval pipeline makes per question."""
    response = _client.chat(
        model=settings.chat_model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        options={"temperature": temperature, "num_predict": max_tokens},
        keep_alive=KEEP_ALIVE,
    )
    return response["message"]["content"].strip()


def chat_with_tools(
    messages: list[dict],
    tools: list[dict],
    temperature: float = 0.1,
    max_tokens: int = 600,
) -> ollama.ChatResponse:
    return _client.chat(
        model=settings.chat_model,
        messages=messages,
        tools=tools,
        options={"temperature": temperature, "num_predict": max_tokens},
        keep_alive=KEEP_ALIVE,
    )


def warm_up() -> None:
    embed_one("warm up")
    complete("Answer with one word.", "Ready?", max_tokens=8)

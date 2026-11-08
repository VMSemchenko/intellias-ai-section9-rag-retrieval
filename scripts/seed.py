import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from docs_assistant import db, ingest, ollama_client  # noqa: E402
from docs_assistant.settings import settings  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Load the corpus into pgvector.")
    parser.add_argument("--reset", action="store_true", help="drop and recreate the tables")
    parser.add_argument(
        "--contextual",
        action="store_true",
        help="add section-05 contextual prefixes — one LLM call per chunk, much slower",
    )
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--limit", type=int, default=0, help="ingest only the first N documents")
    args = parser.parse_args()

    if args.reset:
        print("resetting schema")
        db.reset()
    else:
        db.apply_schema()

    documents = ingest.load_corpus()
    if args.limit:
        documents = documents[: args.limit]

    print(
        f"{len(documents)} documents | embeddings {settings.embedding_model} "
        f"| contextual prefixes {'on' if args.contextual else 'off'}"
    )
    print("warming up ollama (the first call loads the model into memory)")
    ollama_client.warm_up()

    started = time.monotonic()
    last_line = {"phase": ""}

    def report(phase: str, done: int, total: int) -> None:
        if phase != last_line["phase"]:
            print(f"\n  {phase}: ", end="", flush=True)
            last_line["phase"] = phase
        elapsed = time.monotonic() - started
        print(f"\r  {phase}: {done}/{total} chunks  {elapsed:5.0f}s", end="", flush=True)

    result = ingest.ingest(
        documents,
        contextual=args.contextual,
        concurrency=args.concurrency,
        on_progress=report,
    )
    elapsed = time.monotonic() - started

    totals = db.count_rows()
    print(
        f"\n\ningested {result['documents']} documents / {result['chunks']} chunks "
        f"in {elapsed:.1f}s (skipped {result['skipped']} unchanged)"
    )
    print(f"index now holds {totals['documents']} documents / {totals['chunks']} chunks")
    if not args.contextual:
        print("\nno contextual prefixes — add them later with: seed.py --reset --contextual")


if __name__ == "__main__":
    main()

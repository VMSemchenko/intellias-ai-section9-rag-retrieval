import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CORPUS_DIR = PROJECT_ROOT / "corpus"
GOLDEN_SET_PATH = PROJECT_ROOT / "golden_set.json"

load_dotenv(PROJECT_ROOT / ".env")


@dataclass(frozen=True)
class Settings:
    database_url: str
    ollama_host: str
    embedding_model: str
    embedding_dimensions: int
    chat_model: str
    max_agent_iterations: int


def load_settings() -> Settings:
    return Settings(
        database_url=os.getenv(
            "DATABASE_URL", "postgresql://docs:docs@localhost:5434/docs_assistant"
        ),
        ollama_host=os.getenv("OLLAMA_HOST", "http://localhost:11434"),
        embedding_model=os.getenv("EMBEDDING_MODEL", "embeddinggemma:300m"),
        embedding_dimensions=int(os.getenv("EMBEDDING_DIMENSIONS", "768")),
        chat_model=os.getenv("CHAT_MODEL", "qwen2.5:7b-instruct"),
        max_agent_iterations=int(os.getenv("MAX_AGENT_ITERATIONS", "6")),
    )


settings = load_settings()

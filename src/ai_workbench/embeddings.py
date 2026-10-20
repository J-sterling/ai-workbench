"""Text embeddings via Token Factory."""

import time

from ai_workbench import usage
from ai_workbench.config import settings
from ai_workbench.llm import client

# Qwen3-Embedding is instruction-aware: queries get a task prefix, documents don't.
QUERY_INSTRUCTION = (
    "Given an error log from a failed infrastructure run, "
    "retrieve the runbook that explains its root cause and fix"
)


def embed(texts: list[str]) -> list[list[float]]:
    t0 = time.monotonic()
    resp = client.embeddings.create(
        model=settings.embedding_model,
        input=texts,
        dimensions=settings.embedding_dim,
    )
    u = resp.usage
    usage.record("embed", settings.embedding_model, u.prompt_tokens if u else 0, 0, time.monotonic() - t0, "retrieval")
    return [d.embedding for d in sorted(resp.data, key=lambda d: d.index)]


def embed_query(text: str) -> list[float]:
    return embed([f"Instruct: {QUERY_INSTRUCTION}\nQuery: {text}"])[0]

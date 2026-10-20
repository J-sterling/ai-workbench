"""Runbook knowledge base: markdown files -> chunks -> pgvector (or memory).

KB_BACKEND=pgvector (default) searches Postgres. KB_BACKEND=memory embeds runbooks/
once at first use and searches in Python: no database, for single-container deploys.
"""

import math
import re
import threading
from dataclasses import dataclass
from pathlib import Path

import psycopg

from ai_workbench.config import settings
from ai_workbench.embeddings import embed, embed_query

# Runbooks are short, so most stay whole: symptoms, cause and fix in one chunk
# retrieves better than split sections. Only long files are split by "## ".
MAX_CHUNK_CHARS = 6000

# Lines worth embedding from a log; the rest (PLAY banners, ok: lines) is noise.
SIGNAL = re.compile(r"fatal|failed|error|stderr|refused|denied|timeout|timed out|not found|unable|could not|#", re.I)


# Below this cosine similarity a runbook is treated as unrelated.
MIN_SCORE = 0.45


@dataclass
class Hit:
    source: str
    title: str
    content: str
    score: float  # cosine similarity, 1.0 = identical


def title_of(text: str, fallback: str) -> str:
    m = re.search(r"^# (.+)$", text, re.M)
    return m.group(1).strip() if m else fallback


def chunk_markdown(text: str) -> list[str]:
    if len(text) <= MAX_CHUNK_CHARS:
        return [text]
    title = title_of(text, "")
    parts = re.split(r"(?m)^(?=## )", text)
    return [parts[0]] + [f"# {title}\n\n{p}" for p in parts[1:]]


def log_query(log: str, max_chars: int = 4000) -> str:
    """Reduce a log to its error-bearing lines for retrieval."""
    lines = [ln.strip() for ln in log.splitlines() if SIGNAL.search(ln)]
    return ("\n".join(lines) or log)[:max_chars]


def vec(v: list[float]) -> str:
    return "[" + ",".join(f"{x:.6f}" for x in v) + "]"


def connect() -> psycopg.Connection:
    # Fail fast instead of hanging every request when the database stops answering.
    return psycopg.connect(settings.database_url, connect_timeout=5, options="-c statement_timeout=10000")


def ingest_dir(path: Path) -> int:
    """(Re)load every *.md file in path and drop removed ones. Returns the number of chunks stored."""
    files = sorted(path.glob("*.md"))
    total = 0
    with connect() as conn:
        for f in files:
            text = f.read_text()
            chunks = chunk_markdown(text)
            vectors = embed(chunks)
            source = f"runbooks/{f.name}"
            conn.execute("DELETE FROM documents WHERE source = %s", (source,))
            doc_id = conn.execute(
                "INSERT INTO documents (source, title) VALUES (%s, %s) RETURNING id",
                (source, title_of(text, f.stem)),
            ).fetchone()[0]
            with conn.cursor() as cur:
                cur.executemany(
                    "INSERT INTO chunks (document_id, content, embedding) VALUES (%s, %s, %s::vector)",
                    [(doc_id, c, vec(v)) for c, v in zip(chunks, vectors)],
                )
            total += len(chunks)
        # Drop runbooks whose file was deleted or moved, so they stop being retrieved.
        conn.execute(
            "DELETE FROM documents WHERE source LIKE 'runbooks/%%' AND NOT (source = ANY(%s))",
            ([f"runbooks/{f.name}" for f in files],),
        )
    return total


RUNBOOKS = Path(__file__).parent.parent.parent / "runbooks"
_memory: list[tuple[Hit, list[float]]] = []
_memory_lock = threading.Lock()


def _memory_index() -> list[tuple[Hit, list[float]]]:
    with _memory_lock:
        if not _memory:
            items = []
            for f in sorted(RUNBOOKS.glob("*.md")):
                text = f.read_text()
                for chunk in chunk_markdown(text):
                    items.append(Hit(f"runbooks/{f.name}", title_of(text, f.stem), chunk, 0.0))
            vectors = embed([h.content for h in items])
            _memory.extend(zip(items, vectors))
        return _memory


def _cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b)) / (math.hypot(*a) * math.hypot(*b))


def search(query: str, k: int = 3) -> list[Hit]:
    if settings.kb_backend == "memory":
        q = embed_query(query)
        scored = [Hit(h.source, h.title, h.content, _cosine(q, v)) for h, v in _memory_index()]
        return sorted(scored, key=lambda h: h.score, reverse=True)[:k]
    q = vec(embed_query(query))
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT d.source, d.title, c.content, 1 - (c.embedding <=> %s::vector) AS score
            FROM chunks c JOIN documents d ON d.id = c.document_id
            ORDER BY c.embedding <=> %s::vector
            LIMIT %s
            """,
            (q, q, k),
        ).fetchall()
    return [Hit(*r) for r in rows]


def relevant(query: str, k: int = 3) -> list[Hit]:
    """Like search(), but drops hits too weak to count as a match."""
    return [h for h in search(query, k) if h.score >= MIN_SCORE]

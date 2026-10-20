"""Pure KB helpers and the in-memory backend, with fake embeddings (no network, no database)."""

from ai_workbench import kb
from ai_workbench.config import settings


def test_log_query_keeps_error_lines():
    log = "PLAY [x] ****\nok: [a]\nfatal: [a]: FAILED! connection refused\n# operator notes: port 3900\n"
    assert kb.log_query(log) == "fatal: [a]: FAILED! connection refused\n# operator notes: port 3900"


def test_chunking_and_titles():
    assert kb.chunk_markdown("# T\n\nshort") == ["# T\n\nshort"]
    long = "# Title\n\nintro\n" + "".join(f"## S{i}\n" + "x" * 2000 + "\n" for i in range(4))
    chunks = kb.chunk_markdown(long)
    assert len(chunks) == 5 and all(c.startswith("# Title") for c in chunks)
    assert kb.title_of("no heading", "fallback") == "fallback"


def test_memory_backend_ranks_by_cosine(monkeypatch):
    def fake_embed(texts):  # 2-d vectors: garage runbook points one way, everything else the other
        return [[1.0, 0.0] if "garage" in t.lower() and "Garage" in t.split("\n")[0] else [0.0, 1.0] for t in texts]
    monkeypatch.setattr(settings, "kb_backend", "memory")
    monkeypatch.setattr(kb, "embed", fake_embed)
    monkeypatch.setattr(kb, "embed_query", lambda q: [1.0, 0.1])
    monkeypatch.setattr(kb, "_memory", [])
    hits = kb.search("connection refused 3900", k=2)
    assert hits[0].source == "runbooks/s3-backend-garage-down.md"
    assert hits[0].score > 0.99 > hits[1].score


def test_relevant_drops_weak_hits(monkeypatch):
    monkeypatch.setattr(kb, "search", lambda q, k=3: [kb.Hit("a", "A", "", 0.8), kb.Hit("b", "B", "", 0.2)])
    assert [h.source for h in kb.relevant("x")] == ["a"]

"""Load runbooks/*.md into Postgres + pgvector. Safe to re-run.

Run: uv run scripts/ingest_runbooks.py
"""

from pathlib import Path

from ai_workbench.kb import ingest_dir

if __name__ == "__main__":
    n = ingest_dir(Path(__file__).parent.parent / "runbooks")
    print(f"Stored {n} chunks")

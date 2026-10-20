CREATE EXTENSION IF NOT EXISTS vector;

-- Knowledge base: source documents split into embedded chunks.
CREATE TABLE IF NOT EXISTS documents (
    id          bigserial PRIMARY KEY,
    source      text NOT NULL UNIQUE,
    title       text,
    created_at  timestamptz NOT NULL DEFAULT now()
);

-- Qwen/Qwen3-Embedding-8B at 1024 dims (EMBEDDING_DIM); HNSW indexes need <= 2000 dims.
CREATE TABLE IF NOT EXISTS chunks (
    id           bigserial PRIMARY KEY,
    document_id  bigint NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    content      text NOT NULL,
    embedding    vector(1024) NOT NULL
);

CREATE INDEX IF NOT EXISTS chunks_embedding_idx ON chunks USING hnsw (embedding vector_cosine_ops);

-- Run log: every agent run, its tool calls, approvals and token usage.
CREATE TABLE IF NOT EXISTS runs (
    id                 bigserial PRIMARY KEY,
    input              text NOT NULL,
    model              text NOT NULL,
    output             text,
    tool_calls         jsonb NOT NULL DEFAULT '[]',
    status             text NOT NULL DEFAULT 'running',  -- running | awaiting_approval | done | failed
    prompt_tokens      int,
    completion_tokens  int,
    created_at         timestamptz NOT NULL DEFAULT now()
);

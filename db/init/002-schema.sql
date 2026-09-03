-- Core schema for the document review agent.
-- Runs automatically on first container init, after 001-extensions.sql.

CREATE TABLE IF NOT EXISTS documents (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    filename    TEXT NOT NULL,
    source      TEXT,                                   -- e.g. 'upload', 's3://bucket/key'
    status      TEXT NOT NULL DEFAULT 'processing',      -- processing | awaiting_approval | complete | rejected | failed
    thread_id   TEXT,                                    -- LangGraph checkpoint thread id for this run
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- One row per extracted/flagged item, scored against the review schema.
CREATE TABLE IF NOT EXISTS findings (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id         UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    field_name          TEXT NOT NULL,                   -- schema field this finding relates to
    value               TEXT,
    severity            TEXT NOT NULL DEFAULT 'info',     -- info | warning | anomaly | critical
    confidence          REAL,                             -- model's confidence, 0.0-1.0
    citation            TEXT,                             -- source text / page reference backing this finding
    requires_approval   BOOLEAN NOT NULL DEFAULT false,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Chunked + embedded document text, for retrieval during extraction.
CREATE TABLE IF NOT EXISTS document_chunks (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id   UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    chunk_index   INT NOT NULL,
    content       TEXT NOT NULL,
    embedding     VECTOR(1536),                           -- dimension matches the embedding model in use
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS document_chunks_embedding_idx
    ON document_chunks USING hnsw (embedding vector_cosine_ops);

-- Append-only compliance/audit trail — separate from Langfuse's dev-facing traces.
CREATE TABLE IF NOT EXISTS audit_log (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id   UUID REFERENCES documents(id) ON DELETE CASCADE,
    actor         TEXT NOT NULL,                          -- 'agent' | a human's email | 'system'
    action        TEXT NOT NULL,                          -- 'extracted_finding' | 'flagged_anomaly' | 'approved' | 'rejected' | 'resumed'
    detail        JSONB,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Runs automatically the first time the container initializes its data volume.
-- Enables pgvector for embedding storage / similarity search.
CREATE EXTENSION IF NOT EXISTS vector;

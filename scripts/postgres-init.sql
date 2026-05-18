-- Local dev Postgres initialisation.
-- Runs once on first container start. The pgvector extension is created here
-- so the Alembic baseline migration can reference vector columns when the
-- embedding storage decision lands in Prompt 11 — until then the extension
-- is dormant.

CREATE EXTENSION IF NOT EXISTS vector;

# ADR-0002: Postgres 16 with pgvector and pg_search over ChromaDB

**Status:** Accepted
**Date:** 2026-04-16
**Deciders:** Ezra O'Marley

## Context

Afya Gemma v1 used ChromaDB as the vector store and Firestore as the application state store. Across production operation we hit three classes of bugs that were structural, not incidental:

1. Embedding dimension mismatches when we rotated embedding models. ChromaDB's schema migration story was manual and painful.
2. Hybrid retrieval (dense plus BM25) required a second system. We bolted BM25 onto a separate process, which made ranking fusion stateful and hard to reason about.
3. Firestore's document model mismatched the relational nature of our application data (clinician queries, grades, eval runs, calibration sets). Joining across documents required application-side stitching and produced async-in-sync bugs.

The revised architecture consolidates storage into one engine that can do dense vectors, sparse lexical search, structural metadata filtering, and relational application state in a single transaction.

## Decision

Postgres 16 with the following extensions is the single storage substrate:

- **pgvector** for dense vector search (HNSW index, cosine distance)
- **pg_search** (ParadeDB's Tantivy-backed extension) for BM25 lexical search
- **pgcrypto** for at-rest encryption of PHI-adjacent columns
- **pg_stat_statements** for query telemetry
- **pg_cron** for scheduled maintenance (reindex, VACUUM, calibration quantile recompute)

Application access is via asyncpg only. No ORM. Raw parameterized queries in a typed repository layer.

Every chunk carries structural metadata in a JSONB column (section path, visual emphasis flags, table lineage, page range, bounding box, source document hash). This metadata is queryable alongside the vector and text search.

## Consequences

**Positive**

- One backup story, one restore story, one query language. Postgres is a well-understood substrate with known failure modes.
- Hybrid retrieval fuses in a single SQL statement with Reciprocal Rank Fusion. No cross-process state.
- Structural metadata filters compose with vector search natively. We can ask "dense-search the malaria treatment section of guidelines published after 2024 that are pediatric-specific" in one query.
- asyncpg gives us true async without the Firestore sync-in-async traps that bit us repeatedly.
- Schema migrations via Alembic are versioned and reviewable.

**Negative**

- We are not using a purpose-built vector database, which means we do not get features like Pinecone's namespacing or Weaviate's GraphQL. We consider these non-requirements.
- HNSW index builds are memory-intensive. At our corpus size (approximately 15,000 chunks growing to 100,000) this is fine but needs monitoring.
- We need Postgres tuning expertise for shared_buffers, work_mem, effective_cache_size. This is in scope.

**Neutral**

- ChromaDB data must be migrated. The ingestion pipeline reindexes from source PDFs, so the migration is a full reingest, not a data transform. This is actually cleaner.

## Alternatives considered

- **Keep ChromaDB, add separate BM25 service**: rejected, see context.
- **Weaviate**: capable but adds GraphQL and another cluster. Overkill for our corpus size.
- **Qdrant**: strong vector engine but again separate from app state.
- **OpenSearch**: good for hybrid, but the operational cost is significantly higher than Postgres and we don't need its scale.
- **LanceDB**: interesting file-based option. Revisit if we move to edge deployments.

## Compliance and references

- Postgres 16.2+ required (pg_search needs PG 16)
- HNSW parameters: m=16, ef_construction=64, ef_search tuned per query
- Schema migrations live in `backend/alembic/versions/`
- Related: ADR-0004 (ingestion produces structural metadata consumed by this layer)

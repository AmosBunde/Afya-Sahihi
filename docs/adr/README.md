# Architecture Decision Records — Afya Sahihi

Decisions that shape the rebuild. Each ADR is numbered, dated, and immutable once accepted. To change a decision, write a new ADR that supersedes the old one.

## Index

| ID | Title | Status | Date |
|----|-------|--------|------|
| [ADR-0001](./0001-self-host-medgemma-on-vllm.md) | Self-host MedGemma on vLLM instead of Vertex AI endpoints | Accepted | 2026-04-16 |
| [ADR-0002](./0002-postgres-over-chromadb.md) | Postgres 16 with pgvector and pg_search over ChromaDB | Accepted | 2026-04-16 |
| [ADR-0003](./0003-explicit-state-machine-over-langgraph.md) | Explicit Python state machine over LangGraph for orchestration | Accepted | 2026-04-16 |
| [ADR-0004](./0004-docling-structural-ingestion.md) | Docling with structural metadata on every chunk | Accepted | 2026-04-16 |
| [ADR-0005](./0005-k3s-over-full-kubernetes.md) | k3s with systemd watcher over full Kubernetes | Accepted | 2026-04-16 |
| [ADR-0006](./0006-inspect-ai-three-tier-evals.md) | Inspect AI with three-tier eval harness as center of gravity | Accepted | 2026-04-16 |
| [ADR-0007](./0007-medgemma-4b-dual-role.md) | MedGemma 4B as both pre-filter classifier and speculative draft | Accepted | 2026-04-16 |

## ADR lifecycle

- **Proposed**: opened as PR for discussion
- **Accepted**: merged, immutable
- **Deprecated**: still valid but no longer recommended
- **Superseded**: replaced by a newer ADR; link both ways

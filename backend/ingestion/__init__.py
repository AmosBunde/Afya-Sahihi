"""Afya Sahihi offline ingestion pipeline.

ADR-0004 requires every chunk to carry structural metadata (section path,
visual emphasis, table lineage, bounding boxes). This package owns that
extraction: PDF → Docling HybridChunker → structural metadata → embedding
→ idempotent batch insert.

The pipeline is offline only — ADR-0004 and SKILL.md §0 keep Docling and
embedding models off the request path. The CLI entrypoint is
`backend/ingestion/__main__.py`, intended to run inside the CronJob
manifest at `deploy/k3s/50-jobs/ingestion-cronjob.yaml`.
"""

from __future__ import annotations

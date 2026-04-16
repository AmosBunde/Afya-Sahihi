"""CLI entrypoint for the CronJob.

Expected invocation inside the ingestion container:

    python -m ingestion --manifest /etc/afya-sahihi/manifest.yaml

Parses the manifest, builds the real Docling + BGE-M3 + asyncpg stack,
runs `IngestionPipeline.run`, exits 0 on success (including all-skipped)
and 1 on any failure. Retries and scheduling are handled by the
CronJob's `backoffLimit`, not here.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

import asyncpg

from ingestion.docling_chunker import DoclingChunker
from ingestion.embedder import BgeM3Embedder
from ingestion.pipeline import IngestionPipeline
from ingestion.protocols import SourceDocument
from ingestion.repository import AsyncpgIngestionRepository
from ingestion.settings import IngestionSettings

logger = logging.getLogger("afya_sahihi.ingestion")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m ingestion")
    parser.add_argument(
        "--manifest",
        type=Path,
        required=True,
        help="Path to the YAML manifest of PDFs to ingest.",
    )
    return parser.parse_args()


async def _amain() -> int:
    args = _parse_args()
    settings = IngestionSettings()  # reads env per SettingsConfigDict

    logging.basicConfig(
        level=logging.INFO,
        format='{"ts":"%(asctime)s","level":"%(levelname)s","msg":"%(message)s"}',
    )

    documents = tuple(_load_manifest(args.manifest))
    if not documents:
        logger.warning("manifest yielded zero documents; nothing to do")
        return 0

    pool = await asyncpg.create_pool(
        host=settings.pg_host,
        port=settings.pg_port,
        database=settings.pg_database,
        user=settings.pg_user,
        password=settings.pg_password,
        min_size=1,
        max_size=settings.worker_concurrency,
        command_timeout=settings.worker_timeout_seconds,
    )
    try:
        chunker = DoclingChunker(settings=settings)
        embedder = BgeM3Embedder(settings=settings)
        repo = AsyncpgIngestionRepository(pool)
        pipeline = IngestionPipeline(
            settings=settings,
            chunker=chunker,
            embedder=embedder,
            repository=repo,
            chunker_version=f"hybrid-{settings.docling_version}",
        )
        report = await pipeline.run(documents)
    finally:
        await pool.close()

    logger.info(
        "ingestion run complete",
        extra={
            "n_succeeded": len(report.succeeded),
            "n_skipped": len(report.skipped),
            "n_failed": len(report.failed),
        },
    )
    return 1 if report.failed else 0


def _load_manifest(path: Path) -> list[SourceDocument]:
    """Placeholder loader — real manifest parsing lands with the S3 source.

    The manifest format is YAML mapping document_id to {s3_uri, sha256}.
    Until the S3 client is wired in issue #14, the CronJob passes a
    prebuilt list via the --manifest argument pointing at a file that
    adheres to the final format; a noop implementation is acceptable
    here so the CLI fails fast if called before #14 lands.
    """
    raise NotImplementedError(
        "Manifest loader lands with issue #14 (Redis + pgBackRest + "
        "corpus bucket wiring). Until then, the CronJob stays in "
        "preview-only mode."
    )


def main() -> int:
    return asyncio.run(_amain())


if __name__ == "__main__":
    sys.exit(main())

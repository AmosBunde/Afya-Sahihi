"""Pydantic settings for the ingestion pipeline.

Every field mirrors a key in env/ingestion.env (enforced by the
scripts/hooks/check_env_documented.sh hook). Frozen + strict so a typo
fails fast at startup rather than silently at run time.
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class IngestionSettings(BaseSettings):
    """Configuration for one ingestion job invocation.

    Values are read once at process start; the settings object is injected
    into every component thereafter. SKILL.md §11.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        frozen=True,
        extra="ignore",
    )

    service_name: str = "afya-sahihi-ingestion"

    # Source
    source_bucket: str
    source_prefix: str = ""
    source_manifest_path: str

    # Docling
    docling_version: str = "2.9.0"
    docling_pipeline: str = "standard"
    docling_ocr_enabled: bool = True
    docling_ocr_languages: str = "eng,swa"
    docling_extract_tables: bool = True
    docling_extract_figures: bool = True

    # Chunker
    chunker: str = "hybrid"
    chunker_max_tokens: int = Field(default=512, ge=64, le=4096)
    chunker_min_tokens: int = Field(default=64, ge=1)
    chunker_overlap_tokens: int = Field(default=64, ge=0)
    chunker_merge_peers: bool = True
    chunker_tokenizer: str = "BAAI/bge-m3"

    # Structural metadata
    structural_metadata_enabled: bool = True
    structural_capture_bbox: bool = True
    structural_capture_section_path: bool = True
    structural_capture_visual_emphasis: bool = True
    structural_capture_table_lineage: bool = True
    structural_max_section_depth: int = Field(default=6, ge=1, le=10)
    emphasis_rules_path: str = "/etc/afya-sahihi/ingestion/emphasis_rules.yaml"

    # Embedder
    embedder_model: str = "BAAI/bge-m3"
    embedder_device: str = "cpu"
    embedder_batch_size: int = Field(default=32, ge=1, le=256)
    embedder_max_length: int = Field(default=512, ge=1)
    embedder_normalize: bool = True
    embedder_matryoshka_dim: int = Field(default=1024, ge=64, le=4096)

    # Destination
    pg_host: str
    pg_port: int = Field(default=5432, ge=1, le=65535)
    pg_database: str
    pg_user: str
    pg_password: str = Field(repr=False)
    ingestion_batch_insert_size: int = Field(default=500, ge=1, le=5000)
    ingestion_on_duplicate: str = Field(default="skip", pattern="^(skip|replace|error)$")

    # Provenance
    provenance_hash_algorithm: str = "sha256"

    # Idempotency
    idempotency_key_strategy: str = "document_hash_plus_chunker_version"
    idempotency_skip_if_unchanged: bool = True

    # Concurrency
    worker_concurrency: int = Field(default=4, ge=1, le=64)
    worker_timeout_seconds: int = Field(default=600, ge=1, le=3600)
    worker_retry_attempts: int = Field(default=3, ge=0, le=10)

    # Quality gates
    quality_min_chunks_per_doc: int = Field(default=3, ge=0)
    quality_max_chunks_per_doc: int = Field(default=5000, ge=1)
    quality_min_avg_chunk_tokens: int = Field(default=40, ge=1)
    quality_reject_on_failure: bool = True

    # Corpus version — the pipeline stamps every chunk with this value
    # and uses it as one of the idempotency keys.
    corpus_version: str = "v1.0"

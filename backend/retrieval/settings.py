"""Retrieval service configuration. Mirrors env/retrieval.env."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class RetrievalSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        frozen=True,
        extra="ignore",
    )

    service_name: str = "afya-sahihi-retrieval"
    service_port: int = 8081

    # Postgres
    pg_host: str
    pg_port: int = Field(default=5432, ge=1, le=65535)
    pg_database: str
    pg_user: str
    pg_password: str = Field(repr=False)
    pg_pool_min: int = Field(default=4, ge=1)
    pg_pool_max: int = Field(default=20, ge=1)

    # Dense
    retrieval_dense_enabled: bool = True
    dense_similarity_metric: str = "cosine"
    dense_ef_search: int = Field(default=40, ge=1, le=200)
    dense_top_k_candidates: int = Field(default=30, ge=1, le=200)

    # Sparse
    retrieval_sparse_enabled: bool = True
    sparse_top_k_candidates: int = Field(default=30, ge=1, le=200)

    # RRF
    rrf_k_constant: int = Field(default=60, ge=1, le=200)
    fusion_dense_weight: float = Field(default=0.6, ge=0.0, le=1.0)
    fusion_sparse_weight: float = Field(default=0.4, ge=0.0, le=1.0)

    # Reranker
    retrieval_rerank_enabled: bool = True
    reranker_model_path: str = ""
    reranker_device: str = "cpu"
    reranker_batch_size: int = Field(default=16, ge=1, le=128)

    # Structural
    structural_filters_enabled: bool = True
    structural_boost_contraindications: float = Field(default=1.5, ge=1.0, le=5.0)

    # Cache
    query_cache_enabled: bool = True
    query_cache_ttl_seconds: int = Field(default=900, ge=0)

    # Corpus
    corpus_version: str = "v1.0"

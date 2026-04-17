"""Gateway settings. Mirrors env/gateway.env. SKILL.md §11."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        frozen=True,
        extra="ignore",
    )

    service_name: str = "afya-sahihi-gateway"
    service_port: int = 8080

    # Postgres
    pg_host: str = "localhost"
    pg_port: int = 5432
    pg_database: str = "afya-sahihi"
    pg_user: str = "afya_sahihi_app"
    pg_password: str = Field(default="", repr=False)
    pg_pool_min: int = 4
    pg_pool_max: int = 20

    # vLLM
    vllm_27b_base_url: str = "http://localhost:8000"
    vllm_27b_timeout_seconds: float = 60.0
    vllm_4b_base_url: str = "http://localhost:8001"
    vllm_4b_timeout_seconds: float = 10.0

    # Pipeline
    pipeline_prefilter_threshold: float = 0.65
    pipeline_generation_temperature: float = 0.1
    pipeline_generation_seed: int = 20260416

    # Feature flags
    feature_strict_review_enabled: bool = True
    feature_conformal_enabled: bool = True
    orchestrator_fail_closed: bool = True

    # Redis
    redis_host: str = "localhost"
    redis_port: int = 6379

    # Rate limits
    rate_limit_per_user_per_minute: int = 30
    rate_limit_per_user_per_day: int = 500
    rate_limit_burst: int = 10

    # OIDC
    oidc_issuer_url: str = ""
    oidc_audience: str = "afya-sahihi"
    oidc_jwks_uri: str = ""

    # SSE
    sse_keepalive_interval_seconds: int = 15
    sse_max_stream_duration_seconds: int = 120

    # Shutdown
    shutdown_drain_seconds: int = 15

    # Corpus
    corpus_version: str = "v1.0"

    # CORS
    cors_allowed_origins: str = "https://afya-sahihi.aku.edu"

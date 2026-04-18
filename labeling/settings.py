"""Labeling service settings. Mirrors env/labeling.env. SKILL.md §11."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class LabelingSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        frozen=True,
        extra="ignore",
    )

    service_name: str = "afya-sahihi-labeling"
    service_port: int = 8085

    # Postgres
    pg_host: str = "localhost"
    pg_port: int = 5432
    pg_database: str = "afya-sahihi"
    pg_user: str = "afya_sahihi_app"
    pg_password: str = Field(default="", repr=False)
    pg_pool_min: int = 2
    pg_pool_max: int = 8
    pg_statement_timeout_ms: int = 5000

    # Redis
    redis_host: str = "localhost"
    redis_port: int = 6379

    # Queue
    labeling_queue_key: str = "afya-sahihi:labeling:queue"
    labeling_queue_max_per_reviewer_per_day: int = 30

    # Rubric
    rubric_version: str = "v1"

    # Agreement
    dual_rater_ratio: float = 0.2
    kappa_alert_threshold: float = 0.7

    # PDF viewer
    pdf_viewer_base_url: str = "https://afya-sahihi.aku.edu/provenance"
    pdf_viewer_highlight_bbox: bool = True

    # OIDC (shared with gateway)
    oidc_issuer_url: str = ""
    oidc_audience: str = "afya-sahihi"
    oidc_jwks_uri: str = ""

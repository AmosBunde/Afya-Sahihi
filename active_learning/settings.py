"""Active-learning scheduler settings. Mirrors env/eval.env §AL_."""

from __future__ import annotations

from pydantic import Field, HttpUrl, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ActiveLearningSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        frozen=True,
        extra="ignore",
    )

    service_name: str = "afya-sahihi-al-scheduler"
    service_port: int = 8087

    # Core AL knobs
    al_enabled: bool = True
    al_acquisition_function: str = "conformal_set_size"
    al_batch_size: int = 20
    al_control_arm_ratio: float = 0.3
    al_round_cron: str = "0 6 * * 1"
    al_seed: str = "afya-sahihi-al-v1"  # deterministic arm assignment

    # Research governance — a missing or invalid OSF URL blocks startup.
    al_preregistration_url: HttpUrl = Field(...)

    # Paths
    al_initial_pool_path: str = "/srv/afya-sahihi/eval/datasets/al_initial_pool.jsonl"
    al_labeled_pool_table: str = "al_labeled_pool"

    # Postgres + Redis for queue push
    pg_host: str = "localhost"
    pg_port: int = 5432
    pg_database: str = "afya-sahihi"
    pg_user: str = "afya_sahihi_app"
    pg_password: str = Field(default="", repr=False)
    pg_pool_min: int = 2
    pg_pool_max: int = 6
    pg_statement_timeout_ms: int = 5000

    redis_host: str = "localhost"
    redis_port: int = 6379
    labeling_queue_key: str = "afya-sahihi:labeling:queue"

    # Observability
    otel_exporter_otlp_endpoint: str = ""
    deployment_env: str = "dev"
    git_sha: str = "unknown"

    @field_validator("al_control_arm_ratio")
    @classmethod
    def _ratio_in_open_unit(cls, v: float) -> float:
        # 0 or 1 defeats the causal comparison; refuse at startup rather
        # than silently ship with a degenerate arm split.
        if not (0.0 < v < 1.0):
            raise ValueError(f"al_control_arm_ratio must be in (0, 1); got {v}")
        return v

    @field_validator("al_preregistration_url")
    @classmethod
    def _osf_only(cls, v: HttpUrl) -> HttpUrl:
        # Paper P3 must be pre-registered on OSF before any labels are
        # collected. A placeholder URL at deploy time is a research
        # ethics violation; we block startup.
        host = v.host or ""
        if not host.endswith("osf.io"):
            raise ValueError(f"al_preregistration_url must be on osf.io; got {host}")
        path = str(v.path or "")
        if path in ("/", "/xxxxx", ""):
            raise ValueError(
                "al_preregistration_url must point at a real OSF project, "
                "not the env template placeholder"
            )
        return v

    @field_validator("al_batch_size")
    @classmethod
    def _batch_size_positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("al_batch_size must be > 0")
        return v

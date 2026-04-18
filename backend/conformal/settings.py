"""Conformal service settings. Mirrors env/conformal.env."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ConformalSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        frozen=True,
        extra="ignore",
    )

    service_name: str = "afya-sahihi-conformal"
    service_port: int = 8082

    # Postgres
    pg_host: str = "localhost"
    pg_port: int = Field(default=5432, ge=1, le=65535)
    pg_database: str = "afya-sahihi"
    pg_user: str = "afya_sahihi_app"
    pg_password: str = Field(default="", repr=False)

    # Conformal method + coverage target
    cp_method: str = Field(
        default="weighted_split",
        pattern="^(split|weighted_split|adaptive|mondrian)$",
    )
    cp_target_coverage: float = Field(default=0.90, gt=0.0, lt=1.0)
    cp_alpha: float = Field(default=0.10, gt=0.0, lt=1.0)

    # Score selection
    nonconformity_score: str = Field(
        default="clinical_harm_weighted",
        pattern="^(nll|retrieval_weighted|topic_coherence_adjusted|"
        "ensemble_disagreement|clinical_harm_weighted)$",
    )

    # Stratification
    cp_strata: str = "domain,language,facility_level,query_complexity"
    calibration_set_min_size_per_stratum: int = Field(default=100, ge=1)
    calibration_set_max_size: int = Field(default=10000, ge=1)

    # Clinical harm weights (must match env/conformal.env)
    harm_weight_catastrophic: float = Field(default=10.0, gt=0.0)
    harm_weight_major: float = Field(default=3.0, gt=0.0)
    harm_weight_moderate: float = Field(default=1.0, gt=0.0)
    harm_weight_minor: float = Field(default=0.3, gt=0.0)

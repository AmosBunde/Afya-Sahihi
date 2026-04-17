"""Training configuration for the prefilter classifier head.

Frozen Pydantic model so every training run is reproducible from its
config alone. See docs/models/prefilter-v1.md for the model card.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class PrefilterTrainConfig(BaseModel):
    """All hyperparameters for one fine-tuning run."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    # Base model
    base_model: str = "google/medgemma-4b-it"
    base_revision: str = ""

    # LoRA
    lora_r: int = Field(default=16, ge=1, le=128)
    lora_alpha: int = Field(default=32, ge=1, le=256)
    lora_dropout: float = Field(default=0.05, ge=0.0, le=0.5)
    lora_target_modules: tuple[str, ...] = ("q_proj", "v_proj")

    # Dataset
    dataset_path: str = "eval/datasets/prefilter_train.jsonl"
    val_fraction: float = Field(default=0.2, gt=0.0, lt=1.0)
    n_intents: int = Field(default=42, ge=2, le=200)
    max_seq_length: int = Field(default=512, ge=64, le=4096)

    # Training
    epochs: int = Field(default=3, ge=1, le=20)
    batch_size: int = Field(default=16, ge=1, le=128)
    learning_rate: float = Field(default=2e-4, gt=0.0, le=1.0)
    weight_decay: float = Field(default=0.01, ge=0.0, le=1.0)
    warmup_ratio: float = Field(default=0.1, ge=0.0, le=1.0)
    gradient_accumulation_steps: int = Field(default=2, ge=1, le=32)
    seed: int = 20260417

    # Safety head
    safety_threshold: float = Field(default=0.5, ge=0.0, le=1.0)

    # Output
    output_dir: str = "outputs/prefilter-v1"
    adapter_name: str = "afya-sahihi-prefilter-v1"

    # Targets
    target_intent_f1: float = Field(default=0.85, ge=0.0, le=1.0)
    target_safety_recall: float = Field(default=0.95, ge=0.0, le=1.0)

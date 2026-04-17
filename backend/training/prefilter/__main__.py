"""CLI entrypoint for prefilter classifier training.

Usage:
    python -m training.prefilter [--config path/to/config.json]

Requires GPU + Unsloth + TRL (installed via the [training] optional
dep group in pyproject.toml). The training run produces:
    {output_dir}/adapter/       — LoRA adapter weights (safetensors)
    {output_dir}/head.safetensors — classifier head weights
    {output_dir}/eval_report.json — F1 + safety recall report
    {output_dir}/config.json    — frozen training config for
                                   reproducibility

The adapter is then uploaded to MinIO and referenced by
`env/vllm-4b.env VLLM_LORA_MODULES`.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from training.prefilter.config import PrefilterTrainConfig
from training.prefilter.data import load_dataset

logger = logging.getLogger("afya_sahihi.training.prefilter")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m training.prefilter")
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="JSON config file; defaults are used for unset fields.",
    )
    return parser.parse_args()


def main() -> int:
    logging.basicConfig(level=logging.INFO)
    args = _parse_args()

    if args.config and args.config.exists():
        config = PrefilterTrainConfig.model_validate_json(args.config.read_text())
    else:
        config = PrefilterTrainConfig()

    # Save config for reproducibility
    out = Path(config.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "config.json").write_text(config.model_dump_json(indent=2))

    logger.info("loading dataset from %s", config.dataset_path)
    dataset = load_dataset(config)
    logger.info(
        "loaded %d train, %d val, %d intents",
        len(dataset.train),
        len(dataset.val),
        len(dataset.intent_labels),
    )

    # The actual LoRA fine-tuning loop requires Unsloth + TRL + GPU.
    # Import lazily so the config/data/evaluate code stays testable
    # without PyTorch installed.
    try:
        from training.prefilter.train import train_lora
    except ImportError as exc:
        logger.error(
            "training deps not installed: %s. " "Install with: uv sync --extra training",
            exc,
        )
        return 1

    adapter_path = train_lora(config=config, dataset=dataset)
    logger.info("adapter saved to %s", adapter_path)

    # Evaluate on held-out val set

    logger.info("evaluating on %d val samples", len(dataset.val))
    # Placeholder: the real evaluation calls the trained model for
    # predictions. Until then, report structure is validated by
    # backend/training/prefilter/tests/test_evaluate.py.
    logger.warning(
        "inference-based evaluation requires the adapter + base model "
        "loaded in vLLM or torch. Run the eval separately after training "
        "completes. See docs/models/prefilter-v1.md §Evaluation."
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())

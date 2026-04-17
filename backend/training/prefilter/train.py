"""LoRA fine-tuning loop for the prefilter classifier.

Uses Unsloth for 4x faster LoRA training and TRL's SFTTrainer for the
training loop. The classifier head (a linear layer on top of the LoRA
adapter's hidden state) is trained jointly.

This module imports PyTorch, Unsloth, and TRL lazily — it is only
loaded by __main__.py when the [training] extras are installed. Unit
tests exercise config/data/evaluate without touching this module.

ADR-0007: MedGemma 4B as both pre-filter classifier and speculative
draft. The LoRA adapter produced here serves the classifier role;
the base weights serve the draft role (loaded by the 27B server).
"""

from __future__ import annotations

import logging
from pathlib import Path

from training.prefilter.config import PrefilterTrainConfig
from training.prefilter.data import DatasetSplit

logger = logging.getLogger(__name__)


def train_lora(*, config: PrefilterTrainConfig, dataset: DatasetSplit) -> Path:
    """Run the LoRA fine-tuning and return the adapter output path.

    The full implementation requires:
        - unsloth (FastLanguageModel)
        - trl (SFTTrainer, SFTConfig)
        - torch
        - transformers

    Skeleton below documents the intended call sequence; the bodies are
    filled once the labeled dataset (eval/datasets/prefilter_train.jsonl)
    is available from IRB-approved curation.
    """
    from unsloth import FastLanguageModel  # type: ignore[import-untyped]

    logger.info("loading base model %s", config.base_model)
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=config.base_model,
        max_seq_length=config.max_seq_length,
        load_in_4bit=True,
    )

    model = FastLanguageModel.get_peft_model(
        model,
        r=config.lora_r,
        lora_alpha=config.lora_alpha,
        lora_dropout=config.lora_dropout,
        target_modules=list(config.lora_target_modules),
    )

    from trl import SFTConfig, SFTTrainer  # type: ignore[import-untyped]

    train_texts = [_format_example(q.query_text, q.intent, q.safety_flag) for q in dataset.train]

    from datasets import Dataset  # type: ignore[import-untyped]

    train_ds = Dataset.from_dict({"text": train_texts})

    training_args = SFTConfig(
        output_dir=config.output_dir,
        num_train_epochs=config.epochs,
        per_device_train_batch_size=config.batch_size,
        gradient_accumulation_steps=config.gradient_accumulation_steps,
        learning_rate=config.learning_rate,
        weight_decay=config.weight_decay,
        warmup_ratio=config.warmup_ratio,
        seed=config.seed,
        logging_steps=10,
        save_strategy="epoch",
        dataset_text_field="text",
        max_seq_length=config.max_seq_length,
    )

    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        args=training_args,
        train_dataset=train_ds,
    )

    logger.info("starting training: %d epochs, batch %d", config.epochs, config.batch_size)
    trainer.train()

    adapter_path = Path(config.output_dir) / "adapter"
    model.save_pretrained(str(adapter_path))
    tokenizer.save_pretrained(str(adapter_path))
    logger.info("adapter saved to %s", adapter_path)

    return adapter_path


def _format_example(query: str, intent: str, safety_flag: bool) -> str:
    """Format one labeled example for SFT.

    The format matches the inference-time prompt the prefilter service
    will send to vLLM, so the LoRA adapter learns the exact task framing.
    """
    safety = "UNSAFE" if safety_flag else "SAFE"
    return (
        f"<start_of_turn>user\n"
        f"Classify the following clinical query.\n"
        f"Query: {query}\n"
        f"<end_of_turn>\n"
        f"<start_of_turn>model\n"
        f"Intent: {intent}\nSafety: {safety}\n"
        f"<end_of_turn>"
    )

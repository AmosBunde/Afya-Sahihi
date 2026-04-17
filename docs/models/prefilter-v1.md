# Model card: afya-sahihi-prefilter-v1

## Overview

| Field | Value |
|-------|-------|
| **Base model** | google/medgemma-4b-it |
| **Adapter type** | LoRA (r=16, alpha=32, target: q_proj + v_proj) |
| **Task** | Clinical intent classification (42 classes) + binary safety flag |
| **Training framework** | Unsloth + TRL SFTTrainer |
| **Training data** | 2000–5000 labeled queries from AKU retrospective logs (IRB AKU-IRB-2026-0147) |
| **Languages** | English (`en`), Swahili (`sw`), code-switched (`en-sw`) |
| **License** | Internal use; follows the MedGemma license terms |
| **Version** | v1 (initial) |

## Intended use

The adapter serves as the **pre-filter classifier** in the Afya Sahihi
inference pipeline (ADR-0007). It runs on the MedGemma 4B server
(port 8001) via vLLM's LoRA adapter loading and determines:

1. **Topic coherence**: is the query a clinical question the system can
   answer? Queries below the `prefilter_threshold` (default 0.65) are
   refused.
2. **Safety flag**: does the query involve dosing, contraindications,
   pediatrics, or pregnancy? Flagged queries trigger the strict-review
   stage in the orchestrator.
3. **Classified intent**: one of 42 canonical intent labels used for
   conformal stratification and retrieval filter selection.

## Training procedure

```bash
python -m training.prefilter --config training_config.json
```

- LoRA fine-tuning on the base model's q_proj and v_proj attention
  matrices.
- SFT on a prompt template that frames classification as a
  structured-output generation task (see `train.py::_format_example`).
- 3 epochs, batch 16, lr 2e-4, warmup 10%, weight decay 0.01.
- Deterministic seed 20260417 for reproducibility.

## Evaluation

| Metric | Target | Achieved |
|--------|--------|----------|
| Intent F1 (macro, 42 classes) | ≥ 0.85 | *pending training run* |
| Safety recall | ≥ 0.95 | *pending training run* |
| Safety precision | — (reported, not gated) | *pending training run* |
| Inference latency (4B + head) | < 50 ms | *pending deployment measurement* |

Evaluation is run on the 20% held-out validation set via
`training.prefilter.evaluate`. Per-intent F1 breakdown is in
`{output_dir}/eval_report.json`.

## Limitations

- The 42-intent label set was designed for the AKU clinical context
  (Kenyan MoH guidelines). Deploying at a facility with a different
  disease burden requires re-labeling and re-training.
- Swahili and code-switched queries are under-represented in the
  initial training set; expect lower per-language F1 until the active
  learning loop (issue #37) enriches those strata.
- The safety flag heuristic errs on the side of over-flagging. A
  query falsely flagged as safety-critical goes through the slow
  strict-review path but still gets an answer; a query falsely
  cleared skips strict review, which is the failure mode to watch.

## Ethical considerations

- Training data is PHI-scrubbed before labeling (using
  `app.validation.phi.scrub`).
- The model does NOT generate clinical advice; it only classifies
  the intent and safety level of a query. The generation model
  (MedGemma 27B) produces the actual response.
- Misclassification risk: a wrongly-classified intent may route the
  query to a less relevant retrieval filter, degrading answer quality
  but not directly producing a harmful output. The conformal
  prediction layer (issue #25) provides a second check.

## Artifacts

| Artifact | Location | Format |
|----------|----------|--------|
| LoRA adapter | `s3://afya-sahihi-corpus/models/afya-sahihi-prefilter-v1/adapter/` | safetensors |
| Classifier head | `s3://afya-sahihi-corpus/models/afya-sahihi-prefilter-v1/head.safetensors` | safetensors |
| Eval report | `s3://afya-sahihi-corpus/models/afya-sahihi-prefilter-v1/eval_report.json` | JSON |
| Training config | `s3://afya-sahihi-corpus/models/afya-sahihi-prefilter-v1/config.json` | JSON |
| This model card | `docs/models/prefilter-v1.md` | Markdown |

## References

- ADR-0007: MedGemma 4B as both pre-filter classifier and speculative draft
- Issue #17: fine-tune classifier head on 2000–5000 labeled clinical intents
- IRB approval: AKU-IRB-2026-0147

# ADR-0007: MedGemma 4B as both pre-filter classifier and speculative draft model

**Status:** Accepted
**Date:** 2026-04-16
**Deciders:** Ezra O'Marley

## Context

Afya Gemma v1 used Gemini 2.5 Flash as the pre-filter before MedGemma generated a response. This mixed two model families (Gemini and MedGemma), two tokenizers, two billing surfaces, and two failure modes. When a pre-filter decision disagreed with the generation in a surprising way, we could not tell whether it was a tokenization artifact, a prompt formatting quirk, or a real safety signal.

The v2 architecture requires a pre-filter and wants speculative decoding to improve latency on the 27B. A single 4B model can do both jobs.

## Decision

One instance of MedGemma 4B runs on the H100 alongside MedGemma 27B. It serves two roles:

1. **Pre-filter classifier head**. A small classifier layer is fine-tuned on 2,000 to 5,000 labeled clinical intents. The head reads the 4B's final hidden state and outputs a topic coherence score and a safety flag. This is a cheap inference (under 50ms on H100).

2. **Speculative draft model**. vLLM's speculative decoding accepts a smaller "draft" model that proposes tokens which the larger model verifies. MedGemma 4B as draft for MedGemma 27B as target has vocabulary and tokenizer compatibility by design (same model family), which makes speculative decoding work without a bridge.

Both roles share the same weights. SM partitioning on the H100 allocates roughly 20 percent of the GPU to the 4B, 80 percent to the 27B.

## Consequences

**Positive**

- One model family, one tokenizer, one set of update procedures. Failure modes are easier to reason about.
- Speculative decoding typically yields 1.5x to 2.5x speedup on the 27B for clinical text (which has high local token predictability: drug names, dosing schedules, anatomy).
- The classifier head is trained on our own data and can be retrained in-house when drift is detected.
- No external API calls for the pre-filter. The request path no longer depends on Google availability.

**Negative**

- Fine-tuning the classifier head requires labeled intent data. We budget 3 weeks of curation to produce the initial 2,000 intents.
- SM partitioning on H100 is a tunable. We need to monitor for contention under peak load. Mitigation: if contention becomes a problem, colocating 4B onto a separate smaller GPU (RTX 6000 Ada) is a clean upgrade path.
- We lose the "second opinion from a different model family" signal that Gemini provided. This was more narrative than real; empirically, disagreement rate was under 3 percent.

**Neutral**

- The strict-review stage (for safety-critical categories like dosing and contraindications) still runs on the 27B with a dedicated prompt. This is different from the pre-filter and is not affected by this ADR.

## Classifier head architecture

- Input: 4B's final hidden state (dimension 3072)
- Layer 1: linear 3072 → 512, GeLU, dropout 0.1
- Layer 2: linear 512 → N_intents (multi-class) and linear 512 → 1 (safety binary)
- Loss: cross-entropy for intents + BCE for safety, weighted sum
- Training: LoRA adapter on the 4B base so we do not update the 27B speculative compatibility

## Speculative decoding configuration

- `speculative_model`: medgemma-4b-it
- `num_speculative_tokens`: 5 (tune per workload, start conservative)
- `spec_decoding_acceptance_method`: rejection_sampler

## Alternatives considered

- **Keep Gemini Flash as pre-filter**: rejected on cross-family complexity and external dependency.
- **Separate 4B for pre-filter, different draft model for speculative**: rejected on GPU memory grounds; we do not have capacity for two 4B copies.
- **Use 27B itself for classification via zero-shot prompting**: rejected on latency; pre-filter must be under 100ms.

## Compliance and references

- MedGemma 4B weights pulled from HuggingFace with SHA verification
- Classifier head weights version-controlled separately; production weights tag `clf-v1.0`
- Speculative decoding params in `env/vllm-27b.env`
- Related: ADR-0001 (self-host decision), ADR-0003 (orchestrator handles the pre-filter call)

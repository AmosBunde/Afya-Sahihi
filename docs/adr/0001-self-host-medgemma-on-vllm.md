# ADR-0001: Self-host MedGemma on vLLM instead of Vertex AI endpoints

**Status:** Accepted
**Date:** 2026-04-16
**Deciders:** Ezra O'Marley
**Consulted:** AKU infrastructure team, Uzima-DS technical leads

## Context

Afya Gemma v1 ran MedGemma through Vertex AI managed endpoints. During the eighteen-month operating period we observed four recurring problems:

1. Latency was non-deterministic. P99 spiked to 15 seconds during regional load events, which made clinician trust erode and made controlled experiments impossible.
2. We could not obtain token-level logprobs from Vertex, which blocks any conformal prediction work that uses generation likelihoods as nonconformity scores. The calibration paper (P1 of the PhD arc) and the methodological paper (P2) both require these.
3. Query logs left AKU's data perimeter. For a system processing Kenyan clinical queries, this raised ongoing questions with the AKU IRB and with NACOSTI about jurisdiction of PHI-adjacent data.
4. Cost scaled linearly with query volume with no tier for research-mode bulk inference.

The revised architecture prioritizes determinism, token-level introspection, data residency, and predictable cost.

## Decision

We will self-host MedGemma 27B and MedGemma 4B on bare-metal H100 hardware using vLLM as the inference server, exposed via the OpenAI-compatible HTTP API. vLLM will run outside Kubernetes on a dedicated GPU node managed by systemd.

Quantization: FP8 for the 27B, BF16 for the 4B. Prefix caching on. Speculative decoding using the 4B as draft for the 27B (see ADR-0007).

## Consequences

**Positive**

- Token-level logprobs and top-k logprobs are first-class outputs of the OpenAI-compatible API and unblock conformal prediction research.
- P99 latency becomes a function of our own tuning, not a shared cloud tenant. We target P99 under 4 seconds for 512-token responses.
- All PHI-adjacent query text stays on AKU hardware. The IRB conversation gets simpler.
- Cost becomes fixed at the hardware amortization rate rather than per-token.
- vLLM's prefix caching reduces latency on repeated system prompts by roughly 40 to 60 percent based on internal benchmarks.

**Negative**

- We now operate a GPU node. If the H100 fails, the whole inference path fails. Mitigation: the system already degrades gracefully to a "refuse and recommend escalation" response when generation is unavailable. A second H100 is not yet in budget; this is accepted single-point-of-failure risk for the first deployment year.
- Upgrading the model family requires a planned maintenance window rather than a Vertex config change.
- We need in-house skill for vLLM tuning (max_num_batched_tokens, gpu_memory_utilization, speculative_config). This is already within Ezra's skill set and is documented in the implementation skill.

**Neutral**

- Observability must be built in-house via OTel, since Vertex's managed observability is no longer available. This is already planned in the observability stack.

## Alternatives considered

- **Stay on Vertex AI**: rejected on logprob access and data residency grounds.
- **Run MedGemma on TGI (Hugging Face Text Generation Inference)**: TGI is excellent but vLLM has better throughput on PagedAttention and better speculative decoding support as of April 2026.
- **SGLang**: very promising, especially for structured decoding. Retain as a Q4 2026 reevaluation candidate.
- **Ollama**: not suitable for production multi-tenant concurrency.

## Compliance and references

- vLLM version pinned in `env/vllm-27b.env` with SHA-verified container image
- H100 provisioning via AKU infrastructure capital budget line item FY26-AI-002
- Related: ADR-0007 (speculative decoding setup)

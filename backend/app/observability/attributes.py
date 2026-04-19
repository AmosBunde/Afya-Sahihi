"""Canonical span attribute names.

Avoid magic strings at call sites. Every application-authored span
attribute is defined here so a grep for `AfyaAttr.QUERY_ID` finds every
place that sets it. Upstream OTel semantic conventions live in the
`opentelemetry.semconv` package — use those for http/db/rpc attributes;
these constants cover the Afya-Sahihi-specific slice.

Naming rules:
  - Lowercase, dot-delimited, prefixed `afya_sahihi.`
  - Nouns for identifiers (afya_sahihi.query.id), adjective for scalar
    measurements (afya_sahihi.retrieval.top1_similarity).
  - Keep cardinality bounded — don't put query_text or free-form user
    strings here. They belong in logs, not spans.
"""

from __future__ import annotations

from typing import Final


class AfyaAttr:
    """Namespaced constants for Afya Sahihi span attributes."""

    # Identity
    QUERY_ID: Final = "afya_sahihi.query.id"
    USER_ID: Final = "afya_sahihi.user.id"
    REQUEST_ID: Final = "afya_sahihi.request.id"
    CORPUS_VERSION: Final = "afya_sahihi.corpus.version"

    # Orchestrator
    ORCH_STEP: Final = "afya_sahihi.orchestrator.step"
    ORCH_FAIL_CLOSED: Final = "afya_sahihi.orchestrator.fail_closed"

    # Prefilter
    PREFILTER_TOPIC_SCORE: Final = "afya_sahihi.prefilter.topic_score"
    PREFILTER_SAFETY_FLAG: Final = "afya_sahihi.prefilter.safety_flag"
    PREFILTER_INTENT: Final = "afya_sahihi.prefilter.classified_intent"

    # Retrieval
    RETRIEVAL_N_CHUNKS: Final = "afya_sahihi.retrieval.n_chunks"
    RETRIEVAL_TOP1_SIM: Final = "afya_sahihi.retrieval.top1_similarity"
    RETRIEVAL_STRATEGY: Final = "afya_sahihi.retrieval.fusion_strategy"

    # Generation (token-level spans link to Phoenix)
    GEN_MODEL: Final = "afya_sahihi.generation.model"
    GEN_N_TOKENS: Final = "afya_sahihi.generation.n_tokens"
    GEN_AVG_LOGPROB: Final = "afya_sahihi.generation.avg_logprob"
    GEN_TEMPERATURE: Final = "afya_sahihi.generation.temperature"
    GEN_SEED: Final = "afya_sahihi.generation.seed"

    # Strict review
    STRICT_APPROVED: Final = "afya_sahihi.strict_review.approved"
    STRICT_REASON: Final = "afya_sahihi.strict_review.reason"

    # Conformal
    CONFORMAL_SET_SIZE: Final = "afya_sahihi.conformal.set_size"
    CONFORMAL_Q_HAT: Final = "afya_sahihi.conformal.q_hat"
    CONFORMAL_COVERED: Final = "afya_sahihi.conformal.covered"
    CONFORMAL_STRATUM: Final = "afya_sahihi.conformal.stratum"

    # Labeling (Tier 3)
    LABELING_CASE_ID: Final = "afya_sahihi.labeling.case_id"
    LABELING_REVIEWER_ROLE: Final = "afya_sahihi.labeling.reviewer_role"
    LABELING_RUBRIC_VERSION: Final = "afya_sahihi.labeling.rubric_version"

    # Result
    RESULT_ERROR_KIND: Final = "afya_sahihi.result.error_kind"


# Resource attributes (set once at tracer init, propagate to all spans).
class AfyaResource:
    SERVICE_NAME: Final = "service.name"
    SERVICE_VERSION: Final = "service.version"
    SERVICE_NAMESPACE: Final = "service.namespace"
    DEPLOYMENT_ENV: Final = "deployment.environment"
    GIT_SHA: Final = "afya_sahihi.git.sha"
    CORPUS_VERSION: Final = "afya_sahihi.corpus.version"

"""Typed error hierarchy for the orchestrator pipeline.

Every error carries a `reason` string and an optional `detail` object.
The API layer maps each subclass to an appropriate HTTP response without
a big isinstance ladder. SKILL.md §6.
"""

from __future__ import annotations


class PipelineError(Exception):
    """Base for any error in the orchestrator pipeline. Always fails closed."""

    def __init__(self, reason: str, detail: object = None) -> None:
        self.reason = reason
        self.detail = detail
        super().__init__(reason)


class ValidationFailed(PipelineError): ...


class PrefilterRejected(PipelineError): ...


class RetrievalFailed(PipelineError): ...


class GenerationFailed(PipelineError): ...


class StrictReviewRejected(PipelineError): ...


class ConformalFailed(PipelineError): ...

"""Tests for the Tier 2 Slack notifier. No real webhook calls."""

from __future__ import annotations

import json

from eval.tier2.notifier import _build_payload, post_to_slack
from eval.tier2.scorers import Tier2Verdict


def _verdict(passed: bool = True, **overrides: object) -> Tier2Verdict:
    base: dict[str, object] = {
        "passed": passed,
        "ece": 0.05,
        "coverage": 0.91,
        "coverage_deviation": 0.01,
        "set_size_mean": 3.5,
        "set_size_change_pct": 0.0,
        "topic_coherence": 0.85,
        "breaches": () if passed else ("ece:0.10>0.08",),
    }
    base.update(overrides)
    return Tier2Verdict(**base)  # type: ignore[arg-type]


def test_build_payload_passing_has_no_breaches_block() -> None:
    payload = _build_payload(_verdict(passed=True), run_id="run-001")
    blocks = payload["blocks"]
    assert isinstance(blocks, list)
    # No breach block when passed — just header + metrics.
    assert len(blocks) == 2
    assert "PASSED" in json.dumps(payload)


def test_build_payload_failing_includes_breaches() -> None:
    payload = _build_payload(
        _verdict(
            passed=False, breaches=("ece:0.10>0.08", "coverage_deviation:0.05>0.03")
        ),
        run_id="run-002",
    )
    text = json.dumps(payload)
    assert "FAILED" in text
    assert "ece:0.10>0.08" in text
    assert "coverage_deviation:0.05>0.03" in text


def test_post_to_slack_skips_when_webhook_unset(monkeypatch) -> None:
    monkeypatch.delenv("SLACK_WEBHOOK_URL", raising=False)
    assert post_to_slack(_verdict()) is False


def test_post_to_slack_fails_soft_on_network_error(monkeypatch) -> None:
    # Set to a URL that will fail DNS or connection — should return
    # False without raising.
    monkeypatch.setenv(
        "SLACK_WEBHOOK_URL", "http://afya-sahihi-nonexistent.invalid/webhook"
    )
    result = post_to_slack(_verdict(), run_id="test")
    assert result is False

"""Slack notifier for nightly Tier 2 results.

Posts to a webhook URL from the SLACK_WEBHOOK_URL env var. Formats the
verdict as a block-kit message so clinicians can see at-a-glance which
thresholds breached. If the webhook is unset or posting fails, logs
the verdict locally — never crashes the eval run on a notifier error.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.request
from urllib.error import URLError

from eval.tier2.scorers import Tier2Verdict

logger = logging.getLogger(__name__)

_TIMEOUT_SECONDS = 10.0


def post_to_slack(verdict: Tier2Verdict, *, run_id: str = "") -> bool:
    """Post the verdict to Slack. Returns True on HTTP 2xx."""
    url = os.environ.get("SLACK_WEBHOOK_URL", "")
    if not url:
        logger.info(
            "slack webhook unset; skipping post",
            extra={"run_id": run_id, "passed": verdict.passed},
        )
        return False

    payload = _build_payload(verdict, run_id=run_id)
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        # URL source is SLACK_WEBHOOK_URL, provisioned via SealedSecret by
        # cluster admin — not user input. urllib is fine; avoids pulling
        # httpx/requests into the eval image just for one POST.
        with urllib.request.urlopen(  # noqa: S310  # nosec B310  # nosemgrep: python.lang.security.audit.dynamic-urllib-use-detected.dynamic-urllib-use-detected
            req, timeout=_TIMEOUT_SECONDS
        ) as resp:
            return 200 <= resp.status < 300
    except (URLError, TimeoutError) as exc:
        logger.warning(
            "slack post failed; verdict logged locally",
            extra={"run_id": run_id, "error": str(exc)},
        )
        return False


def _build_payload(verdict: Tier2Verdict, *, run_id: str) -> dict[str, object]:
    """Slack block-kit formatted verdict."""
    emoji = ":white_check_mark:" if verdict.passed else ":rotating_light:"
    status = "PASSED" if verdict.passed else "FAILED"

    header = f"{emoji} Tier 2 nightly eval: {status}"
    if run_id:
        header = f"{header} (run {run_id})"

    metric_lines = [
        f"• ECE: `{verdict.ece:.4f}` (max 0.08)",
        f"• Coverage deviation: `{verdict.coverage_deviation:.4f}` (max 0.03)",
        f"• Set size change: `{verdict.set_size_change_pct:+.2f}%` (max +15%)",
        f"• Topic coherence: `{verdict.topic_coherence:.4f}` (min 0.80)",
    ]

    blocks: list[dict[str, object]] = [
        {"type": "header", "text": {"type": "plain_text", "text": header}},
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "*Metrics:*\n" + "\n".join(metric_lines),
            },
        },
    ]

    if verdict.breaches:
        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "*Breaches:*\n"
                    + "\n".join(f"• {b}" for b in verdict.breaches),
                },
            }
        )

    return {"blocks": blocks}

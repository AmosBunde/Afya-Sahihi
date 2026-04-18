"""Rolling empirical-coverage calculator.

For each (stratum, observation) pair — where an observation is whether
the ground-truth label fell inside the prediction set — this module
maintains a 24h sliding window and exposes the empirical coverage rate.

The coverage monitor (service in this module) samples from labeled
traffic and emits the Prometheus gauges. When empirical coverage drifts
more than 5pp from target (env/conformal.env COVERAGE_ALERT_THRESHOLD_DEVIATION)
an alert fires (deploy/observability/alerts/conformal.yaml).
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from time import time


@dataclass(frozen=True, slots=True)
class CoverageObservation:
    """One labeled event: was the ground truth in the prediction set?"""

    stratum: str
    covered: bool
    set_size: int
    timestamp: float


@dataclass(frozen=True, slots=True)
class StratumCoverage:
    """Rolling snapshot for one stratum."""

    stratum: str
    n_samples: int
    empirical_coverage: float
    mean_set_size: float
    window_seconds: int


class RollingCoverage:
    """Per-stratum sliding window over `window_seconds`.

    Thread-unsafe by design — the coverage monitor runs as a single
    async task per process. If sharing across processes is needed later,
    back with Redis sorted sets instead of in-memory deques.

    `observe()` prunes expired events lazily on insert, so snapshot
    reads are O(n_fresh) with no background task.
    """

    def __init__(
        self,
        *,
        window_seconds: int = 86400,
        max_samples_per_stratum: int = 10000,
    ) -> None:
        if window_seconds <= 0:
            raise ValueError("window_seconds must be positive")
        self._window = window_seconds
        self._max_samples = max_samples_per_stratum
        self._by_stratum: dict[str, deque[CoverageObservation]] = {}

    def observe(
        self,
        *,
        stratum: str,
        covered: bool,
        set_size: int,
        timestamp: float | None = None,
    ) -> None:
        ts = timestamp if timestamp is not None else time()
        obs = CoverageObservation(stratum=stratum, covered=covered, set_size=set_size, timestamp=ts)
        window = self._by_stratum.setdefault(stratum, deque(maxlen=self._max_samples))
        window.append(obs)
        self._prune(window, now=ts)

    def snapshot(self, stratum: str, *, now: float | None = None) -> StratumCoverage:
        """Return the coverage + mean set size over the active window."""
        t = now if now is not None else time()
        window = self._by_stratum.get(stratum)
        if not window:
            return StratumCoverage(
                stratum=stratum,
                n_samples=0,
                empirical_coverage=0.0,
                mean_set_size=0.0,
                window_seconds=self._window,
            )

        self._prune(window, now=t)
        n = len(window)
        if n == 0:
            return StratumCoverage(
                stratum=stratum,
                n_samples=0,
                empirical_coverage=0.0,
                mean_set_size=0.0,
                window_seconds=self._window,
            )

        covered = sum(1 for o in window if o.covered)
        total_size = sum(o.set_size for o in window)
        return StratumCoverage(
            stratum=stratum,
            n_samples=n,
            empirical_coverage=covered / n,
            mean_set_size=total_size / n,
            window_seconds=self._window,
        )

    def strata(self) -> list[str]:
        """Every stratum that has seen at least one observation."""
        return list(self._by_stratum.keys())

    def _prune(self, window: deque[CoverageObservation], *, now: float) -> None:
        cutoff = now - self._window
        while window and window[0].timestamp < cutoff:
            window.popleft()


def coverage_deviation(empirical: float, target: float) -> float:
    """Signed deviation from target. Positive = over-covering."""
    return empirical - target

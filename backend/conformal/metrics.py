"""Prometheus metrics for the conformal service.

Metric names use the `afya_sahihi_` prefix per SKILL.md §10. Labels
carry the stratum and score_type so Grafana can break out per-stratum
coverage trends. The client is the standard `prometheus_client`; we
expose it via a thin wrapper so tests inject a fake without importing
the library.

Metrics emitted:
    afya_sahihi_conformal_coverage_empirical{stratum}         gauge
    afya_sahihi_conformal_coverage_target                     gauge (constant)
    afya_sahihi_conformal_set_size_mean{stratum}              gauge
    afya_sahihi_conformal_set_size_bucket{stratum, le}        histogram
    afya_sahihi_conformal_drift_mmd{stratum, score_type}      gauge
    afya_sahihi_conformal_drift_detected_total{stratum}       counter

The coverage monitor (service in this module) calls `observe_*` on
each event; Prometheus scrapes /metrics at its configured interval.
"""

from __future__ import annotations

from typing import Protocol


class Metrics(Protocol):
    """Narrow interface the coverage monitor consumes."""

    def set_coverage(self, *, stratum: str, value: float) -> None: ...
    def set_mean_set_size(self, *, stratum: str, value: float) -> None: ...
    def observe_set_size(self, *, stratum: str, value: float) -> None: ...
    def set_drift_mmd(self, *, stratum: str, score_type: str, value: float) -> None: ...
    def inc_drift_detected(self, *, stratum: str) -> None: ...


class PrometheusMetrics(Metrics):
    """Concrete metrics backed by prometheus_client.

    Constructed once at service startup with a shared `registry`
    (default or a test-scoped CollectorRegistry). Re-registering the
    same metric raises; pass `registry=None` for tests that want a
    fresh registry per test.
    """

    def __init__(self, *, registry: object | None = None) -> None:
        from prometheus_client import (  # type: ignore[import-untyped]
            CollectorRegistry,
            Counter,
            Gauge,
            Histogram,
        )

        reg = registry if registry is not None else CollectorRegistry()
        self._registry = reg

        self._coverage = Gauge(
            "afya_sahihi_conformal_coverage_empirical",
            "Empirical marginal coverage over the rolling window, per stratum.",
            labelnames=("stratum",),
            registry=reg,
        )
        self._coverage_target = Gauge(
            "afya_sahihi_conformal_coverage_target",
            "Target marginal coverage 1 - alpha (constant for reference).",
            registry=reg,
        )
        self._set_size_mean = Gauge(
            "afya_sahihi_conformal_set_size_mean",
            "Mean prediction-set size over the rolling window, per stratum.",
            labelnames=("stratum",),
            registry=reg,
        )
        self._set_size_hist = Histogram(
            "afya_sahihi_conformal_set_size",
            "Distribution of prediction-set sizes.",
            labelnames=("stratum",),
            buckets=(1, 2, 3, 5, 10, 20, 50, 100),
            registry=reg,
        )
        self._drift_mmd = Gauge(
            "afya_sahihi_conformal_drift_mmd",
            "MMD² between reference and current score distribution.",
            labelnames=("stratum", "score_type"),
            registry=reg,
        )
        self._drift_detected = Counter(
            "afya_sahihi_conformal_drift_detected_total",
            "Count of drift-threshold crossings, per stratum.",
            labelnames=("stratum",),
            registry=reg,
        )

    @property
    def registry(self) -> object:
        return self._registry

    def set_coverage_target(self, value: float) -> None:
        self._coverage_target.set(value)

    def set_coverage(self, *, stratum: str, value: float) -> None:
        self._coverage.labels(stratum=stratum).set(value)

    def set_mean_set_size(self, *, stratum: str, value: float) -> None:
        self._set_size_mean.labels(stratum=stratum).set(value)

    def observe_set_size(self, *, stratum: str, value: float) -> None:
        self._set_size_hist.labels(stratum=stratum).observe(value)

    def set_drift_mmd(self, *, stratum: str, score_type: str, value: float) -> None:
        self._drift_mmd.labels(stratum=stratum, score_type=score_type).set(value)

    def inc_drift_detected(self, *, stratum: str) -> None:
        self._drift_detected.labels(stratum=stratum).inc()

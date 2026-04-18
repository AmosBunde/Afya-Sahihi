"""Afya Sahihi Tier 3 clinician labeling UI.

Streamlit app that surfaces 20 cases/week/reviewer from a Redis-backed
queue, captures a 5-point rubric score, and persists grades with
chain-of-custody to the `grades` table. A sidecar CronJob computes
Fleiss kappa daily across dual-rated cases and alerts if agreement
drops below the configured threshold.

See ADR-0006 (three-tier evals) and ADR-0009 (Streamlit for labeling).
"""

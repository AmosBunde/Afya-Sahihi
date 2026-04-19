"""Active-learning acquisition scheduler (Paper P3).

Weekly batch of 20 cases per facility: 70% acquisition-function picks,
30% random control arm. Picked cases land on the labeling queue; the
reviewer has no visibility into which arm a case belongs to, so their
grade is the outcome we causally regress on.

Acquisition functions live in `acquisition.py`. Assignment (treatment
vs control, deterministic hash of case_id + reviewer_id + week) lives
in `assignment.py`. Coverage-improvement-per-label estimation lives
in `effect_size.py` with Bayesian posterior intervals. The scheduler
service binds them together (`scheduler.py`); the repository layer
(`repository.py`) reads the candidate pool and writes assignments to
the `al_labeled_pool` table.

See ADR-0013 for the research design and `env/eval.env` §AL_ for the
knobs.
"""

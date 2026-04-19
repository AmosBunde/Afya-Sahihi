"""Paper P1: calibration analysis of MedGemma under distribution shift.

Scored calibration metrics (ECE, MCE, ACE, Brier, reliability-diagram
area) plus baseline calibration methods (temperature scaling, Platt,
histogram binning, ensemble averaging). All pure Python so paper
figures reproduce without scipy/sklearn — the committed code is the
analysis, not a wrapper around them.

See `docs/papers/p1-calibration/` for the paper draft and
reproducibility notes.
"""

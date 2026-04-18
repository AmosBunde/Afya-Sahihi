"""Conformal prediction service.

Implements split conformal (Vovk et al. 2005) with 5 domain-specific
nonconformity scores. The target coverage 1 - alpha is enforced
marginally across the full test distribution; stratified quantiles give
conditional coverage per (language, domain, facility_level) tuple.

ADR-0007 notes + env/conformal.env. Issue #25.
"""

from __future__ import annotations

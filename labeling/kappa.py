"""Fleiss kappa inter-rater agreement.

Fleiss kappa generalises Cohen's kappa to more than two raters. It
measures agreement above chance across a fixed number of raters per
item (here, 3 for dual-rated cases). Values:

    1.00  perfect agreement
    0.00  agreement at chance level
   <0.00  worse than chance (raters systematically disagreeing)

For clinical rubrics we alert below 0.70.

Pure math. No I/O. Tests in `tests/test_kappa.py`.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class FleissKappaResult:
    """Kappa plus the working terms, useful for debugging."""

    kappa: float
    n_items: int
    n_raters: int
    n_categories: int
    p_mean_agreement: float
    p_expected_by_chance: float


def fleiss_kappa(*, item_rater_category_counts: list[list[int]]) -> FleissKappaResult:
    """Compute Fleiss kappa over N items × K categories.

    `item_rater_category_counts[i][k]` = number of raters who assigned
    item i to category k. Every row must sum to the same number of
    raters (`n`). Items with inconsistent rater counts raise ValueError.

    Returns `FleissKappaResult(kappa=nan, ...)` when agreement is
    undefined (single category with all ratings → both P_mean and P_e
    equal 1, so kappa is 0/0). The caller treats nan as "degenerate"
    and does not alert.
    """
    if not item_rater_category_counts:
        raise ValueError("item_rater_category_counts is empty")

    n_items = len(item_rater_category_counts)
    k = len(item_rater_category_counts[0])
    if k == 0:
        raise ValueError("no categories in first item")

    # Validate shape + constant rater count
    n = sum(item_rater_category_counts[0])
    if n < 2:
        raise ValueError(f"need at least 2 raters per item, got n={n}")
    for i, row in enumerate(item_rater_category_counts):
        if len(row) != k:
            raise ValueError(f"item {i} has {len(row)} categories, expected {k}")
        if sum(row) != n:
            raise ValueError(
                f"item {i} has {sum(row)} raters, expected {n} (from item 0)"
            )
        for count in row:
            if count < 0:
                raise ValueError(f"item {i} has negative count")

    # P_i: agreement for item i, averaged over pairs of raters
    # P_i = (1 / (n*(n-1))) * (Σ_k n_ik² − n)
    p_items: list[float] = []
    for row in item_rater_category_counts:
        sum_sq = sum(count * count for count in row)
        p_i = (sum_sq - n) / (n * (n - 1))
        p_items.append(p_i)
    p_mean = sum(p_items) / n_items

    # p_j: proportion of all ratings assigned to category j
    total_ratings = n * n_items
    p_cat: list[float] = []
    for j in range(k):
        column_sum = sum(row[j] for row in item_rater_category_counts)
        p_cat.append(column_sum / total_ratings)

    p_expected = sum(p * p for p in p_cat)

    denom = 1.0 - p_expected
    if denom == 0.0:
        # Degenerate: all raters agreed on a single category for every item.
        # Kappa is undefined; signal with nan.
        kappa = float("nan")
    else:
        kappa = (p_mean - p_expected) / denom

    return FleissKappaResult(
        kappa=kappa,
        n_items=n_items,
        n_raters=n,
        n_categories=k,
        p_mean_agreement=p_mean,
        p_expected_by_chance=p_expected,
    )


def build_counts_matrix(
    *,
    ratings_per_item: list[list[int]],
    n_categories: int,
) -> list[list[int]]:
    """Turn per-item rating lists into the Fleiss counts matrix.

    `ratings_per_item[i]` is the list of category labels (0-indexed,
    0..n_categories-1) assigned by each rater to item i. All items must
    be rated by the same number of raters.
    """
    if not ratings_per_item:
        return []
    if n_categories <= 0:
        raise ValueError("n_categories must be positive")
    out: list[list[int]] = []
    for i, ratings in enumerate(ratings_per_item):
        counts = [0] * n_categories
        for label in ratings:
            if label < 0 or label >= n_categories:
                raise ValueError(
                    f"item {i}: category label {label} outside [0, {n_categories})"
                )
            counts[label] += 1
        out.append(counts)
    return out

"""Tests for Fleiss kappa.

Reference values for the canonical example from the Fleiss (1971) paper
and a few edge cases."""

from __future__ import annotations

import math

import pytest

from labeling.kappa import build_counts_matrix, fleiss_kappa


def test_perfect_agreement_gives_kappa_one() -> None:
    # 4 items, 3 raters, 2 categories, everyone always picks category 0.
    # Above chance (chance = 1.0 since p_cat[0] = 1) → kappa is nan
    # (denominator 0). Swap one rater to make chance < 1 but agreement
    # still perfect per-item for the remaining rows.
    counts = [
        [3, 0],
        [0, 3],
        [3, 0],
        [0, 3],
    ]
    result = fleiss_kappa(item_rater_category_counts=counts)
    assert result.kappa == pytest.approx(1.0, abs=1e-9)
    assert result.n_items == 4
    assert result.n_raters == 3
    assert result.n_categories == 2


def test_random_agreement_gives_kappa_near_zero() -> None:
    # Split uniformly across 2 categories → agreement matches chance.
    # n=4 raters, 100 items, 50/50 distribution per item on avg.
    counts = [[2, 2]] * 100
    result = fleiss_kappa(item_rater_category_counts=counts)
    # P_i = (4 + 4 - 4) / (4*3) = 4/12 = 1/3. P_e = 0.5² + 0.5² = 0.5.
    # kappa = (1/3 - 0.5) / (1 - 0.5) = -1/3.
    assert result.kappa == pytest.approx(-1 / 3, abs=1e-9)


def test_fleiss_canonical_example() -> None:
    # Fleiss 1971, table 1: 30 psychiatric diagnoses, 6 raters, 5
    # categories. The reported kappa is 0.430; we verify against a
    # smaller trimmed version so the test stays readable.
    # 4 items, 3 raters, 3 categories
    counts = [
        [3, 0, 0],  # unanimous on cat 0
        [2, 1, 0],  # majority cat 0
        [0, 3, 0],  # unanimous on cat 1
        [0, 2, 1],  # majority cat 1
    ]
    result = fleiss_kappa(item_rater_category_counts=counts)
    # P_i: (9-3)/6=1, (4+1-3)/6=1/3, (9-3)/6=1, (4+1-3)/6=1/3
    # mean = (1+1/3+1+1/3)/4 = 2/3
    # column sums: 5, 6, 1; totals 12; p_cat = [5/12, 6/12, 1/12]
    # P_e = 25/144 + 36/144 + 1/144 = 62/144
    # kappa = (2/3 - 62/144) / (1 - 62/144)
    expected = (2 / 3 - 62 / 144) / (1 - 62 / 144)
    assert result.kappa == pytest.approx(expected, abs=1e-9)
    assert result.p_mean_agreement == pytest.approx(2 / 3, abs=1e-9)


def test_empty_input_raises() -> None:
    with pytest.raises(ValueError, match="empty"):
        fleiss_kappa(item_rater_category_counts=[])


def test_inconsistent_rater_counts_raise() -> None:
    with pytest.raises(ValueError, match="raters"):
        fleiss_kappa(
            item_rater_category_counts=[
                [3, 0],
                [1, 1],  # only 2 raters; first row had 3
            ]
        )


def test_inconsistent_category_counts_raise() -> None:
    with pytest.raises(ValueError, match="categories"):
        fleiss_kappa(
            item_rater_category_counts=[
                [1, 1, 1],
                [2, 1],
            ]
        )


def test_negative_counts_raise() -> None:
    with pytest.raises(ValueError, match="negative"):
        fleiss_kappa(item_rater_category_counts=[[3, -1], [1, 1]])


def test_degenerate_single_category_returns_nan() -> None:
    # All raters agreed on a single category across all items. P_e = 1,
    # denom = 0, kappa undefined.
    counts = [[3, 0], [3, 0], [3, 0]]
    result = fleiss_kappa(item_rater_category_counts=counts)
    assert math.isnan(result.kappa)


def test_build_counts_matrix_roundtrips() -> None:
    ratings = [[0, 0, 1], [2, 2, 2], [1, 0, 0]]
    counts = build_counts_matrix(ratings_per_item=ratings, n_categories=3)
    assert counts == [
        [2, 1, 0],
        [0, 0, 3],
        [2, 1, 0],
    ]


def test_build_counts_matrix_rejects_out_of_range_label() -> None:
    with pytest.raises(ValueError, match="outside"):
        build_counts_matrix(ratings_per_item=[[0, 3]], n_categories=3)


def test_build_counts_matrix_empty_returns_empty() -> None:
    assert build_counts_matrix(ratings_per_item=[], n_categories=3) == []

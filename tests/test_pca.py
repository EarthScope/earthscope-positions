"""Tests for classical PCA network decomposition (analysis.pca)."""
from __future__ import annotations

import numpy as np
import pytest

from earthscope_positions.analysis import pca


@pytest.fixture
def synthetic_dense():
    """A and B share a strong common-mode signal; C is independent. No gaps."""
    rng = np.random.default_rng(1)
    n = 3 * 86400
    t = np.arange(n, dtype=float)
    shared = 5.0 * np.sin(2 * np.pi * t / 3600.0)

    a = shared + rng.normal(0, 1.0, n)
    b = shared + rng.normal(0, 1.0, n)
    c = rng.normal(0, 1.0, n)
    return {"A": a, "B": b, "C": c}


def test_leading_mode_explains_most_variance(synthetic_dense):
    result = pca.principal_component_analysis(synthetic_dense)
    assert result["geosncls"] == ["A", "B", "C"]
    assert result["n_modes"] == 3
    assert result["n_complete_epochs"] == len(synthetic_dense["A"])  # no gaps
    assert result["eigenvalues"][0] >= result["eigenvalues"][1] >= result["eigenvalues"][2]
    assert result["variance_explained_pct"][0] > 80.0


def test_leading_mode_loads_on_shared_streams_only(synthetic_dense):
    result = pca.principal_component_analysis(synthetic_dense)
    loadings0 = dict(zip(result["geosncls"], result["loadings"][0]))
    assert abs(loadings0["A"]) > 0.5
    assert abs(loadings0["B"]) > 0.5
    assert np.sign(loadings0["A"]) == np.sign(loadings0["B"])
    assert abs(loadings0["C"]) < 0.2


def test_mode_series_matches_shared_signal_shape(synthetic_dense):
    result = pca.principal_component_analysis(synthetic_dense)
    pc = result["mode_series"][0]
    assert pc.shape == synthetic_dense["A"].shape
    assert not np.any(np.isnan(pc))  # no gaps -> every epoch is "complete"

    t = np.arange(len(pc), dtype=float)
    shared = np.sin(2 * np.pi * t / 3600.0)
    corr = abs(np.corrcoef(pc, shared)[0, 1])
    assert corr > 0.9


def test_n_modes_capped_at_stream_count(synthetic_dense):
    result = pca.principal_component_analysis(synthetic_dense, n_modes=10)
    assert result["n_modes"] == 3
    assert len(result["loadings"]) == 3


def test_empty_input():
    result = pca.principal_component_analysis({})
    assert result["geosncls"] == []
    assert result["n_modes"] == 0
    assert result["loadings"] == []


def test_gaps_outside_complete_epochs_are_nan_in_mode_series():
    n = 1000
    a = np.sin(np.arange(n) / 50.0)
    b = np.sin(np.arange(n) / 50.0) + 0.1
    a_gappy = a.copy()
    a_gappy[500:600] = np.nan  # A missing for [500, 600) -> not "complete" there
    result = pca.principal_component_analysis({"A": a_gappy, "B": b})
    assert result["n_complete_epochs"] == n - 100
    pc = result["mode_series"][0]
    assert np.all(np.isnan(pc[500:600]))
    assert not np.any(np.isnan(np.concatenate([pc[:500], pc[600:]])))


def test_common_mode_removed_shrinks_variance_of_shared_streams_only(synthetic_dense):
    residual = pca.pca_common_mode_removed(synthetic_dense, n_modes_removed=1)
    assert set(residual.keys()) == {"A", "B", "C"}
    assert residual["A"].std() < synthetic_dense["A"].std() * 0.5
    assert residual["B"].std() < synthetic_dense["B"].std() * 0.5
    assert abs(residual["C"].std() - synthetic_dense["C"].std()) < 0.05


def test_common_mode_removed_preserves_mean_level(synthetic_dense):
    shifted = dict(synthetic_dense)
    shifted["A"] = shifted["A"] + 100.0
    residual = pca.pca_common_mode_removed(shifted, n_modes_removed=1)
    assert abs(residual["A"].mean() - shifted["A"].mean()) < 1.0


def test_common_mode_removed_leaves_incomplete_epochs_unchanged():
    n = 1000
    a = np.sin(np.arange(n) / 50.0)
    b = np.sin(np.arange(n) / 50.0) + 0.1
    a_gappy = a.copy()
    a_gappy[500:600] = np.nan
    dense = {"A": a_gappy, "B": b}
    residual = pca.pca_common_mode_removed(dense, n_modes_removed=1)
    # B has no gap, but at epochs where A is missing there's no common-mode
    # estimate to remove, so B's own value there must be untouched.
    np.testing.assert_array_equal(residual["B"][500:600], b[500:600])


def test_common_mode_removed_single_stream_is_a_noop():
    dense = {"A": np.array([1.0, 2.0, np.nan, 4.0])}
    residual = pca.pca_common_mode_removed(dense, n_modes_removed=1)
    np.testing.assert_array_equal(residual["A"], dense["A"])


def test_too_few_complete_epochs_is_a_noop():
    # A and B never overlap -> 0 complete epochs -> nothing to remove.
    a = np.array([1.0, 2.0, np.nan, np.nan])
    b = np.array([np.nan, np.nan, 3.0, 4.0])
    dense = {"A": a, "B": b}
    result = pca.principal_component_analysis(dense)
    assert result["n_modes"] == 0
    residual = pca.pca_common_mode_removed(dense, n_modes_removed=1)
    np.testing.assert_array_equal(residual["A"], a)
    np.testing.assert_array_equal(residual["B"], b)

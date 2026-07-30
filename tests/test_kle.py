"""Tests for the Karhunen-Loeve (network PCA) decomposition."""
from __future__ import annotations

import numpy as np
import pytest

from earthscope_positions.analysis import kle


@pytest.fixture
def synthetic_dense():
    """A and B share a strong common-mode signal; C is independent."""
    rng = np.random.default_rng(1)
    n = 3 * 86400
    t = np.arange(n, dtype=float)
    shared = 5.0 * np.sin(2 * np.pi * t / 3600.0)

    a = shared + rng.normal(0, 1.0, n)
    b = shared + rng.normal(0, 1.0, n)
    c = rng.normal(0, 1.0, n)
    return {"A": a, "B": b, "C": c}


def test_leading_mode_explains_most_variance(synthetic_dense):
    result = kle.karhunen_loeve(synthetic_dense)
    assert result["geosncls"] == ["A", "B", "C"]
    assert result["n_modes"] == 3
    assert len(result["eigenvalues"]) == 3
    # descending
    assert result["eigenvalues"][0] >= result["eigenvalues"][1] >= result["eigenvalues"][2]
    assert result["variance_explained_pct"][0] > 80.0


def test_leading_mode_loads_on_shared_streams_only(synthetic_dense):
    result = kle.karhunen_loeve(synthetic_dense)
    loadings0 = dict(zip(result["geosncls"], result["loadings"][0]))
    # A and B (the shared pair) load strongly and with the same sign;
    # C (independent) loads near zero.
    assert abs(loadings0["A"]) > 0.5
    assert abs(loadings0["B"]) > 0.5
    assert np.sign(loadings0["A"]) == np.sign(loadings0["B"])
    assert abs(loadings0["C"]) < 0.2


def test_n_modes_capped_at_stream_count(synthetic_dense):
    result = kle.karhunen_loeve(synthetic_dense, n_modes=10)
    assert result["n_modes"] == 3
    assert len(result["loadings"]) == 3


def test_empty_input():
    result = kle.karhunen_loeve({})
    assert result["geosncls"] == []
    assert result["n_modes"] == 0
    assert result["loadings"] == []


def test_reconstruct_mode_matches_shared_signal_shape(synthetic_dense):
    result = kle.karhunen_loeve(synthetic_dense)
    pc = kle.reconstruct_mode(synthetic_dense, result["geosncls"], result["loadings"][0])
    assert pc.shape == synthetic_dense["A"].shape
    assert not np.any(np.isnan(pc))  # no gaps in this fixture

    # The reconstructed mode should correlate very strongly with the true
    # shared oscillation (sign is arbitrary from the eigendecomposition).
    t = np.arange(len(pc), dtype=float)
    shared = np.sin(2 * np.pi * t / 3600.0)
    corr = abs(np.corrcoef(pc, shared)[0, 1])
    assert corr > 0.9


def test_common_mode_removed_shrinks_variance_of_shared_streams_only(synthetic_dense):
    residual = kle.common_mode_removed(synthetic_dense, n_modes_removed=1)
    assert set(residual.keys()) == {"A", "B", "C"}

    # A and B's std should drop substantially (toward the pure-noise floor,
    # std=1); C (no shared signal) should be essentially unchanged.
    assert residual["A"].std() < synthetic_dense["A"].std() * 0.5
    assert residual["B"].std() < synthetic_dense["B"].std() * 0.5
    assert abs(residual["C"].std() - synthetic_dense["C"].std()) < 0.05


def test_common_mode_removed_preserves_mean_level(synthetic_dense):
    shifted = dict(synthetic_dense)
    shifted["A"] = shifted["A"] + 100.0  # stream has its own large offset
    residual = kle.common_mode_removed(shifted, n_modes_removed=1)
    # Removing a zero-mean common mode should not shift the stream's own level.
    assert abs(residual["A"].mean() - shifted["A"].mean()) < 1.0


def test_common_mode_removed_single_stream_is_a_noop():
    dense = {"A": np.array([1.0, 2.0, np.nan, 4.0])}
    residual = kle.common_mode_removed(dense, n_modes_removed=1)
    np.testing.assert_array_equal(residual["A"], dense["A"])

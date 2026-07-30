"""Tests for pairwise coherence spectra: dense-grid alignment and the shared
log-frequency axis."""
from __future__ import annotations

import numpy as np
import pytest

from earthscope_positions.analysis import coherence as coh


def test_densify_1hz_places_values_and_fills_gaps():
    times_ms = np.array([1000, 3000, 3000, 9000])  # duplicate second: last wins
    values = np.array([1.0, 2.0, 20.0, 4.0])
    out = coh.densify_1hz(times_ms, values, start_ms=0, end_ms=10_000)

    assert out.shape == (10,)
    assert out[1] == 1.0
    assert out[3] == 20.0          # duplicate second — later sample wins
    assert out[9] == 4.0
    assert np.isnan(out[0])
    assert np.isnan(out[5])


def test_densify_1hz_drops_out_of_range_samples():
    times_ms = np.array([-5000, 500, 20_000])
    values = np.array([1.0, 2.0, 3.0])
    out = coh.densify_1hz(times_ms, values, start_ms=0, end_ms=1_000)
    assert out.shape == (1,)
    assert out[0] == 2.0


def test_densify_1hz_empty_range():
    out = coh.densify_1hz(np.array([]), np.array([]), start_ms=0, end_ms=0)
    assert out.shape == (0,)


@pytest.fixture
def synthetic_dense():
    """Two streams sharing a 60-min oscillation, one independent stream, and a
    fourth with too little overlap to be usable — 3 days at 1 Hz."""
    rng = np.random.default_rng(0)
    n = 3 * 86400
    t = np.arange(n, dtype=float)
    shared = 5.0 * np.sin(2 * np.pi * t / 3600.0)  # 60-min period

    a = shared + rng.normal(0, 1.0, n)
    b = shared + rng.normal(0, 1.0, n)
    c = rng.normal(0, 1.0, n)  # independent — no shared component

    d = rng.normal(0, 1.0, n)
    d[: n * 3 // 4] = np.nan  # only 25% valid — should be skipped

    return {"A": a, "B": b, "C": c, "D": d}


def _pair_coherence(result: dict, a: str, b: str) -> list[float]:
    for p in result["pairs"]:
        if {p["a"], p["b"]} == {a, b}:
            return p["coherence"]
    raise AssertionError(f"pair {a}/{b} not found in result (skipped: {result['pairs_skipped']})")


def test_spectra_isolate_shared_frequency(synthetic_dense):
    result = coh.pairwise_coherence_spectra(
        {k: v for k, v in synthetic_dense.items() if k != "D"}
    )
    assert result["geosncls"] == ["A", "B", "C"]
    freqs = np.array(result["frequencies"])
    assert len(freqs) == coh.N_DISPLAY_FREQS
    assert np.all(np.diff(freqs) > 0)  # strictly increasing (log-spaced)

    idx_60min = np.argmin(np.abs(freqs - 1.0 / 3600.0))
    ab = _pair_coherence(result, "A", "B")
    ac = _pair_coherence(result, "A", "C")
    bc = _pair_coherence(result, "B", "C")

    # A and B share the 60-min oscillation — coherence there should clearly
    # exceed the unrelated-pair baseline, and A/B's own coherence away from it.
    assert ab[idx_60min] > 0.9
    assert ab[idx_60min] > 5 * ac[idx_60min]
    assert ab[idx_60min] > 5 * bc[idx_60min]
    # away from the shared frequency, A/B should look like any other pair
    idx_5min = np.argmin(np.abs(freqs - 1.0 / 300.0))
    assert ab[idx_5min] < 0.3


def test_spectra_values_are_bounded_0_1(synthetic_dense):
    result = coh.pairwise_coherence_spectra(
        {k: v for k, v in synthetic_dense.items() if k != "D"}
    )
    for p in result["pairs"]:
        vals = np.array(p["coherence"])
        assert np.all(vals >= 0.0) and np.all(vals <= 1.0)


def test_spectra_skips_insufficient_overlap(synthetic_dense):
    result = coh.pairwise_coherence_spectra(synthetic_dense)
    skipped_pairs = {tuple(sorted((a, b))) for a, b, _reason in result["pairs_skipped"]}
    assert ("A", "D") in skipped_pairs
    assert ("B", "D") in skipped_pairs
    assert ("C", "D") in skipped_pairs
    present_pairs = {(p["a"], p["b"]) for p in result["pairs"]}
    assert not any("D" in pair for pair in present_pairs)


def test_spectra_empty_input():
    result = coh.pairwise_coherence_spectra({})
    assert result["geosncls"] == []
    assert result["n_total"] == 0
    assert result["frequencies"] == []
    assert result["pairs"] == []


def test_spectra_too_little_data_skips_all_pairs():
    dense = {"A": np.zeros(10), "B": np.zeros(10)}  # far below MIN_NPERSEG_S
    result = coh.pairwise_coherence_spectra(dense)
    assert result["pairs"] == []
    assert len(result["pairs_skipped"]) == 1


def test_spectra_zero_power_stream_produces_no_nan():
    """Regression test: a constant (zero-variance) stream detrends to exactly
    zero for every sample, so its power spectral density is exactly zero at
    every non-DC frequency.  scipy's Cxy = |Pxy|^2 / Pxx / Pyy is then a 0/0
    division -> NaN (with a "invalid value encountered in divide"
    RuntimeWarning) unless sanitized.  JSON can't encode NaN at all —
    Starlette's JSONResponse encoder raises ValueError on it outright — so
    this must never leak into the returned coherence values."""
    n = 3 * 86400
    rng = np.random.default_rng(2)
    dense = {
        "A": np.full(n, 5.0),           # constant -> zero power at every non-DC bin
        "B": rng.normal(0, 1.0, n),
    }
    result = coh.pairwise_coherence_spectra(dense)
    assert result["pairs"], "pair should have enough overlap to be computed, not skipped"
    coherence = result["pairs"][0]["coherence"]
    assert all(np.isfinite(v) for v in coherence)
    assert all(0.0 <= v <= 1.0 for v in coherence)

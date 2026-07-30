"""Tests for /api/coherence, /api/kle, and /api/positions/common-mode-removed —
the webserver plumbing (arrow loading, validation, response shape) around
analysis/coherence.py and analysis/kle.py, whose math is covered in
test_coherence.py and test_kle.py."""
from __future__ import annotations

import datetime as dt
import pathlib

import numpy as np
import pyarrow as pa
import pyarrow.ipc as ipc
import pytest

from conftest import make_positions_arrow, POSITIONS_SCHEMA

_UTC = dt.timezone.utc
_START = dt.datetime(2026, 1, 15, tzinfo=_UTC)
_N_ROWS = 90_000  # 25 h at 1 Hz — enough for the adaptive Welch segment sizing


def _write_arrow(data_dir: pathlib.Path, geosncl: str, n_rows: int = _N_ROWS) -> None:
    gsdir = data_dir / "arrow" / geosncl / "202601"
    gsdir.mkdir(parents=True, exist_ok=True)
    end = _START + dt.timedelta(seconds=n_rows)
    fname = f"{geosncl}_{_START.strftime('%Y%m%dT%H%M%SZ')}_{end.strftime('%Y%m%dT%H%M%SZ')}.arrow"
    (gsdir / fname).write_bytes(make_positions_arrow(n_rows, start=_START, as_stream=True))


@pytest.fixture
def client(project_tree):
    from fastapi.testclient import TestClient
    import earthscope_positions.webserver.webserver as w

    _write_arrow(project_tree / "data", "P100.NC.LY_.20")
    _write_arrow(project_tree / "data", "P200.NC.LY_.20")
    w._file_index = w._scan_data_dir_sync(w._data_dir())
    return TestClient(w.app)


_PARAMS = {
    "geosncls": "P100.NC.LY_.20,P200.NC.LY_.20",
    "start": "2026-01-15",
    "end": "2026-01-16",
}


# ── /api/coherence ────────────────────────────────────────────────────────────

def test_coherence_happy_path(client):
    r = client.get("/api/coherence", params=_PARAMS)
    assert r.status_code == 200
    body = r.json()

    assert body["geosncls"] == ["P100.NC.LY_.20", "P200.NC.LY_.20"]
    assert body["component"] == "east"
    assert len(body["frequencies"]) > 0
    assert body["pairs_skipped"] == []
    assert len(body["pairs"]) == 1

    pair = body["pairs"][0]
    assert {pair["a"], pair["b"]} == set(_PARAMS["geosncls"].split(","))
    assert len(pair["coherence"]) == len(body["frequencies"])
    # Identical synthetic streams -> near-perfect coherence throughout.
    assert min(pair["coherence"]) > 0.9


def test_coherence_component_param(client):
    r = client.get("/api/coherence", params={**_PARAMS, "component": "east"})
    assert r.status_code == 200
    assert r.json()["component"] == "east"


def test_coherence_rejects_bad_component(client):
    r = client.get("/api/coherence", params={**_PARAMS, "component": "sideways"})
    assert r.status_code == 422


def test_coherence_rejects_too_few_streams(client):
    r = client.get("/api/coherence", params={**_PARAMS, "geosncls": "P100.NC.LY_.20"})
    assert r.status_code == 400


def test_coherence_accepts_up_to_35_streams(client):
    many = ",".join(f"P{i:03d}.NC.LY_.20" for i in range(35))
    r = client.get("/api/coherence", params={**_PARAMS, "geosncls": many})
    assert r.status_code == 200
    assert len(r.json()["geosncls"]) == 35


def test_coherence_rejects_more_than_35_streams(client):
    many = ",".join(f"P{i:03d}.NC.LY_.20" for i in range(36))
    r = client.get("/api/coherence", params={**_PARAMS, "geosncls": many})
    assert r.status_code == 400


def test_kle_has_no_upper_stream_limit(client):
    many = ",".join(f"P{i:03d}.NC.LY_.20" for i in range(40))
    r = client.get("/api/kle", params={**_PARAMS, "geosncls": many})
    assert r.status_code == 200
    assert len(r.json()["geosncls"]) == 40


def test_pca_has_no_upper_stream_limit(client):
    many = ",".join(f"P{i:03d}.NC.LY_.20" for i in range(40))
    r = client.get("/api/pca", params={**_PARAMS, "geosncls": many})
    assert r.status_code == 200
    assert len(r.json()["geosncls"]) == 40


def test_coherence_rejects_bad_dates(client):
    r = client.get("/api/coherence", params={**_PARAMS, "start": "not-a-date"})
    assert r.status_code == 400


def test_coherence_rejects_end_before_start(client):
    r = client.get("/api/coherence", params={**_PARAMS, "start": "2026-01-16", "end": "2026-01-15"})
    assert r.status_code == 400


# ── /api/kle ──────────────────────────────────────────────────────────────────

def test_kle_happy_path(client):
    r = client.get("/api/kle", params=_PARAMS)
    assert r.status_code == 200
    body = r.json()

    assert body["geosncls"] == ["P100.NC.LY_.20", "P200.NC.LY_.20"]
    assert body["component"] == "east"
    assert body["n_modes"] == 2
    assert len(body["eigenvalues"]) == 2
    assert len(body["variance_explained_pct"]) == 2
    assert len(body["loadings"]) == 2 and len(body["loadings"][0]) == 2
    # Identical synthetic streams share everything -> mode 1 explains ~100%.
    assert body["variance_explained_pct"][0] > 99.0

    # Reconstructed mode time series — one per mode, same length as modeTimes.
    assert len(body["modeTimes"]) > 0
    assert len(body["modeSeries"]) == body["n_modes"]
    assert len(body["modeSeries"][0]) == len(body["modeTimes"])
    assert body["modeDownsampleFactor"] >= 1


def test_kle_n_modes_capped_at_stream_count(client):
    r = client.get("/api/kle", params={**_PARAMS, "n_modes": 10})
    assert r.status_code == 200
    assert r.json()["n_modes"] == 2


def test_kle_rejects_too_few_streams(client):
    r = client.get("/api/kle", params={**_PARAMS, "geosncls": "P100.NC.LY_.20"})
    assert r.status_code == 400


def test_kle_rejects_bad_dates(client):
    r = client.get("/api/kle", params={**_PARAMS, "start": "not-a-date"})
    assert r.status_code == 400


# ── /api/pca ──────────────────────────────────────────────────────────────────

def test_pca_happy_path(client):
    r = client.get("/api/pca", params=_PARAMS)
    assert r.status_code == 200
    body = r.json()

    assert body["geosncls"] == ["P100.NC.LY_.20", "P200.NC.LY_.20"]
    assert body["component"] == "east"
    assert body["n_modes"] == 2
    assert len(body["eigenvalues"]) == 2
    assert len(body["loadings"]) == 2 and len(body["loadings"][0]) == 2
    # Identical synthetic streams fully overlap -> every epoch in the
    # requested 1-day window is complete, and mode 1 explains ~100% of the
    # (shared) variance.
    assert body["n_complete_epochs"] == 86400
    assert body["variance_explained_pct"][0] > 99.0

    assert len(body["modeTimes"]) > 0
    assert len(body["modeSeries"]) == body["n_modes"]
    assert len(body["modeSeries"][0]) == len(body["modeTimes"])
    assert body["modeDownsampleFactor"] >= 1


def test_pca_n_modes_capped_at_stream_count(client):
    r = client.get("/api/pca", params={**_PARAMS, "n_modes": 10})
    assert r.status_code == 200
    assert r.json()["n_modes"] == 2


def test_pca_rejects_too_few_streams(client):
    r = client.get("/api/pca", params={**_PARAMS, "geosncls": "P100.NC.LY_.20"})
    assert r.status_code == 400


def test_pca_rejects_bad_dates(client):
    r = client.get("/api/pca", params={**_PARAMS, "start": "not-a-date"})
    assert r.status_code == 400


def test_pca_mode_series_sampled_from_valid_epochs_not_full_grid(project_tree):
    """Regression test: PCA's mode is only defined where every stream
    overlaps, which can be a small, non-uniformly-placed slice of a much
    longer requested range.  Downsampling by striding the *full* grid (as
    /api/kle does — its mode is defined almost everywhere) can trivially
    miss that slice entirely, returning an all-null series even though
    n_complete_epochs > 0.  One stream spans the whole day; the other only a
    300 s window in the middle — the fix must still return real values."""
    from fastapi.testclient import TestClient
    import earthscope_positions.webserver.webserver as w

    data_dir = project_tree / "data"
    _write_arrow(data_dir, "P100.NC.LY_.20", n_rows=_N_ROWS)  # full-day coverage

    narrow_start = _START + dt.timedelta(seconds=40_000)
    gsdir = data_dir / "arrow" / "P900.NC.LY_.20" / "202601"
    gsdir.mkdir(parents=True, exist_ok=True)
    end = narrow_start + dt.timedelta(seconds=300)
    fname = f"P900.NC.LY_.20_{narrow_start.strftime('%Y%m%dT%H%M%SZ')}_{end.strftime('%Y%m%dT%H%M%SZ')}.arrow"
    (gsdir / fname).write_bytes(make_positions_arrow(300, start=narrow_start, as_stream=True))

    w._file_index = w._scan_data_dir_sync(w._data_dir())
    client = TestClient(w.app)

    r = client.get("/api/pca", params={**_PARAMS, "geosncls": "P100.NC.LY_.20,P900.NC.LY_.20", "max_points": 100})
    assert r.status_code == 200
    body = r.json()
    assert body["n_complete_epochs"] == 300
    assert body["n_modes"] > 0

    non_null = [v for v in body["modeSeries"][0] if v is not None]
    assert non_null, "mode series was entirely null despite n_complete_epochs > 0"


def _write_arrow_with_values(data_dir: pathlib.Path, geosncl: str, east: np.ndarray) -> None:
    """Like _write_arrow, but with explicit per-row east values (everything
    else zeroed) — needed to inject a single gross outlier at a specific row."""
    n = len(east)
    times = [int(_START.timestamp() * 1000) + i * 1000 for i in range(n)]
    table = pa.table(
        {
            "time": times,
            "east": east.tolist(),
            "north": [0.0] * n,
            "up": [0.0] * n,
            "sigEE": [0.01] * n,
            "sigNN": [0.01] * n,
            "sigUU": [0.02] * n,
            "qChannel": [0] * n,
            "ingestLatency": [1500] * n,
            "processingDelay": [200] * n,
        },
        schema=POSITIONS_SCHEMA,
    )
    gsdir = data_dir / "arrow" / geosncl / "202601"
    gsdir.mkdir(parents=True, exist_ok=True)
    end = _START + dt.timedelta(seconds=n)
    fname = f"{geosncl}_{_START.strftime('%Y%m%dT%H%M%SZ')}_{end.strftime('%Y%m%dT%H%M%SZ')}.arrow"
    sink = pa.BufferOutputStream()
    with ipc.new_stream(sink, table.schema) as writer:
        writer.write_table(table)
    (gsdir / fname).write_bytes(sink.getvalue().to_pybytes())


def test_kle_outlier_m_prevents_one_bad_sample_from_dominating(project_tree):
    """Regression test: KLE/PCA/coherence all pick out the *maximum-variance*
    direction, so a single gross bad fix (e.g. a multi-km spike) in an
    otherwise well-behaved, shared-signal stream can inflate that one
    stream's variance by many orders of magnitude and swallow the whole
    decomposition — mode 1 becomes ~100% that one stream, loading ~1.0,
    every other (perfectly normal) stream ~0.  outlier_m must strip the
    spike out before any of that math runs."""
    from fastapi.testclient import TestClient
    import earthscope_positions.webserver.webserver as w

    n = _N_ROWS  # 25 h — file must cover the full requested day plus some
    rng = np.random.default_rng(7)
    t = np.arange(n, dtype=float)
    shared = 0.01 * np.sin(2 * np.pi * t / 3600.0)  # a few-cm shared oscillation
    a = shared + rng.normal(0, 0.002, n)
    b = shared + rng.normal(0, 0.002, n)
    a[40_000] += 12_000.0  # a single 12 km bad fix, well inside the requested day (< 86400)

    # Unique geosncls (not P100/P200 used elsewhere in this file) — the
    # shared _table_cache is process-global and keyed on (geosncl, start_ms,
    # end_ms), so reusing another test's geosncl+date-range combination could
    # serve its cached table instead of the data this test just wrote.
    data_dir = project_tree / "data"
    _write_arrow_with_values(data_dir, "P901.NC.LY_.20", a)
    _write_arrow_with_values(data_dir, "P902.NC.LY_.20", b)
    w._file_index = w._scan_data_dir_sync(w._data_dir())
    client = TestClient(w.app)

    params = {**_PARAMS, "geosncls": "P901.NC.LY_.20,P902.NC.LY_.20"}

    r_raw = client.get("/api/kle", params=params)
    assert r_raw.status_code == 200
    loadings_raw = dict(zip(r_raw.json()["geosncls"], r_raw.json()["loadings"][0]))
    # Without filtering, the spike dominates: essentially all loading on P901,
    # none on P902, even though the rest of their data is a shared signal.
    assert abs(loadings_raw["P901.NC.LY_.20"]) > 0.99

    r_clean = client.get("/api/kle", params={**params, "outlier_m": 5})
    assert r_clean.status_code == 200
    loadings_clean = dict(zip(r_clean.json()["geosncls"], r_clean.json()["loadings"][0]))
    # With the spike rejected, both streams share the mode roughly equally.
    assert abs(loadings_clean["P901.NC.LY_.20"]) > 0.3
    assert abs(loadings_clean["P902.NC.LY_.20"]) > 0.3


# ── /api/positions/common-mode-removed ───────────────────────────────────────

def test_cmr_happy_path(client):
    r = client.get("/api/positions/common-mode-removed", params=_PARAMS)
    assert r.status_code == 200
    body = r.json()

    assert body["nModesRemoved"] == 1
    assert body["method"] == "kle"  # default
    assert "nCompleteEpochs" not in body  # only reported for method=pca
    assert set(body["varianceExplainedPct"].keys()) == {"east", "north", "up"}
    assert len(body["stations"]) == 2

    station = body["stations"][0]
    assert set(station.keys()) == {"geosncl", "times", "east", "north", "up", "downsampleFactor"}
    assert len(station["times"]) == len(station["east"]) == len(station["north"]) == len(station["up"])

    # Identical synthetic streams -> the (only) common mode is essentially the
    # whole time-varying signal, so the residual should collapse to a constant
    # (the stream's own mean — common-mode-removed preserves each stream's own
    # level, it doesn't re-zero it).
    residual_up = [v for v in station["up"] if v is not None]
    assert residual_up
    assert (max(residual_up) - min(residual_up)) < 1e-6


def test_cmr_rejects_too_few_streams(client):
    r = client.get("/api/positions/common-mode-removed", params={**_PARAMS, "geosncls": "P100.NC.LY_.20"})
    assert r.status_code == 400


def test_cmr_respects_max_points(client):
    r = client.get("/api/positions/common-mode-removed", params={**_PARAMS, "max_points": 500})
    assert r.status_code == 200
    body = r.json()
    assert len(body["stations"][0]["times"]) <= 500
    assert body["stations"][0]["downsampleFactor"] >= 1


def test_cmr_downsample_false_returns_full_resolution(client):
    r = client.get("/api/positions/common-mode-removed", params={**_PARAMS, "downsample": False})
    assert r.status_code == 200
    body = r.json()
    assert body["stations"][0]["downsampleFactor"] == 1
    assert len(body["stations"][0]["times"]) == 86400  # full 1 Hz grid for the requested day


def test_cmr_n_modes_removed_param(client):
    r = client.get("/api/positions/common-mode-removed", params={**_PARAMS, "n_modes_removed": 2})
    assert r.status_code == 200
    assert r.json()["nModesRemoved"] == 2


def test_cmr_pca_method_happy_path(client):
    r = client.get("/api/positions/common-mode-removed", params={**_PARAMS, "method": "pca"})
    assert r.status_code == 200
    body = r.json()

    assert body["method"] == "pca"
    assert set(body["nCompleteEpochs"].keys()) == {"east", "north", "up"}
    # Identical, fully-overlapping synthetic streams -> every epoch is complete.
    assert body["nCompleteEpochs"]["up"] == 86400

    residual_up = [v for v in body["stations"][0]["up"] if v is not None]
    assert residual_up
    assert (max(residual_up) - min(residual_up)) < 1e-6


def test_cmr_rejects_bad_method(client):
    r = client.get("/api/positions/common-mode-removed", params={**_PARAMS, "method": "bogus"})
    assert r.status_code == 422

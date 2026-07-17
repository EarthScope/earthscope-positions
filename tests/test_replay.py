"""Unit tests for the replay record generator — payload formats and the
arrival-time windowing option.  These exercise the pure data path (no Kafka)."""
from __future__ import annotations

import datetime as dt
import json
import pathlib

import pytest

from conftest import make_positions_arrow
from earthscope_positions.replay import replay

GEOSNCL = "TEST.CI.LY_.20"
BASE = dt.datetime(2026, 1, 15, tzinfo=dt.timezone.utc)
BASE_MS = int(BASE.timestamp() * 1000)
LATENCY_MS = 1500  # conftest's make_positions_arrow uses a fixed 1500 ms ingestLatency


@pytest.fixture
def arrow_file(tmp_path) -> pathlib.Path:
    """8 rows of 1 Hz data (data_time = BASE + i*1000 ms), stream-format Arrow."""
    p = tmp_path / f"{GEOSNCL}_20260115.arrow"
    p.write_bytes(make_positions_arrow(8, start=BASE, step_ms=1000, as_stream=True))
    return p


def _rows(path, **kwargs):
    return list(replay._file_row_gen(path, GEOSNCL, **kwargs))


def test_compact_format(arrow_file):
    rows = _rows(arrow_file, apply_latency=True)
    assert len(rows) == 8
    arrival, key, val = rows[0]
    assert key == GEOSNCL.encode()
    assert arrival == BASE_MS + LATENCY_MS          # data_time + latency
    rec = json.loads(val)
    assert rec["SNCL"] == GEOSNCL
    assert rec["type"] == "ENU"
    assert rec["time"] == BASE_MS
    assert set(rec) == {"time", "Q", "type", "SNCL", "coor", "err", "rate"}
    assert len(rec["coor"]) == 3 and len(rec["err"]) == 3


def test_geojson_format(arrow_file):
    rows = _rows(arrow_file, apply_latency=True, output_format="geojson")
    assert len(rows) == 8
    _, _, val = rows[0]
    rec = json.loads(val)
    assert rec["type"] == "Feature"
    assert rec["geometry"]["type"] == "Point"
    assert len(rec["geometry"]["coordinates"]) == 3
    props = rec["properties"]
    assert props["SNCL"] == GEOSNCL
    assert props["coordinateType"] == "ENU"
    assert props["time"] == BASE_MS
    assert {"EError", "NError", "UError", "quality", "sampleRate"} <= set(props)


def test_no_latency_arrival_equals_data_time(arrow_file):
    rows = _rows(arrow_file, apply_latency=False)
    arrival, _, val = rows[0]
    assert arrival == BASE_MS                        # no latency added
    assert json.loads(val)["time"] == BASE_MS


def test_window_by_data_time(arrow_file):
    # Window [BASE+2000, BASE+5000] selected by DATA time → indices 2,3,4,5.
    rows = _rows(
        arrow_file, apply_latency=True,
        win_start_ms=BASE_MS + 2000, win_stop_ms=BASE_MS + 5000,
    )
    data_times = sorted(json.loads(v)["time"] for _, _, v in rows)
    assert data_times == [BASE_MS + i * 1000 for i in (2, 3, 4, 5)]


def test_window_by_arrival_time(arrow_file):
    # Same window, selected by ARRIVAL (data_time + 1500 ms).
    # arrival in [BASE+2000, BASE+5000]  ⇔  data_time in [BASE+500, BASE+3500]
    #   → indices 1,2,3 (i=0 arrives too early; i>=4 arrives too late).
    rows = _rows(
        arrow_file, apply_latency=True,
        win_start_ms=BASE_MS + 2000, win_stop_ms=BASE_MS + 5000,
        select_by_arrival=True,
    )
    data_times = sorted(json.loads(v)["time"] for _, _, v in rows)
    assert data_times == [BASE_MS + i * 1000 for i in (1, 2, 3)]
    # A record whose *data* time precedes the window start is still included
    # because its arrival lands inside the window.
    assert (BASE_MS + 1000) in data_times
    # …and every emitted arrival is inside the window.
    for arrival, _, _ in rows:
        assert BASE_MS + 2000 <= arrival <= BASE_MS + 5000

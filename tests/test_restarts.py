"""Gaps, restarts and continuous blocks.

A restart is an outage, so the counts drive an operator-facing plot; the cases
that matter are the boundaries (what is and is not a gap) and the invariant
that per-bin counts still add up to the file's total however the bins are
later aggregated.
"""
from __future__ import annotations

import pathlib

import pyarrow as pa
import pyarrow.ipc as ipc
import pytest

from conftest import make_positions_arrow
from earthscope_positions.process import completeness as C

_HOUR = 3_600_000


def _times(*runs: tuple[int, int]) -> list[int]:
    """Build sample times from (start_ms, n_samples) runs at 1 Hz."""
    out: list[int] = []
    for start, n in runs:
        out.extend(start + i * 1000 for i in range(n))
    return out


# ---------------------------------------------------------------------------
# What counts as a gap
# ---------------------------------------------------------------------------

def test_continuous_series_has_no_gaps():
    times = _times((0, 100))
    assert C.find_gaps(times) == []
    assert len(C.continuous_blocks(times)) == 1


def test_one_dropped_sample_is_not_a_gap():
    """At 1 Hz a lone missing epoch is a 2.000 s interval, and the threshold is
    a strict `>` on 2 s precisely so it is not counted as an outage."""
    times = [0, 1000, 3000, 4000]          # 2000 ms step in the middle
    assert C.find_gaps(times) == []
    assert len(C.continuous_blocks(times)) == 1


def test_two_dropped_samples_is_a_gap():
    times = [0, 1000, 4000, 5000]          # 3000 ms step
    assert C.find_gaps(times) == [(1000, 4000)]
    blocks = C.continuous_blocks(times)
    assert [(s, e, n) for s, e, n in blocks] == [(0, 1000, 2), (4000, 5000, 2)]


def test_threshold_is_configurable():
    times = [0, 1000, 4000]                # a 3 s gap
    assert C.find_gaps(times, gap_seconds=2.0) == [(1000, 4000)]
    assert C.find_gaps(times, gap_seconds=5.0) == []


def test_blocks_are_restarts_plus_one():
    times = _times((0, 10), (60_000, 10), (120_000, 10))
    assert len(C.find_gaps(times)) == 2
    assert len(C.continuous_blocks(times)) == 3


def test_empty_series():
    assert C.find_gaps([]) == []
    assert C.continuous_blocks([]) == []


def test_single_sample_is_one_block():
    assert C.continuous_blocks([5000]) == [(5000, 5000, 1)]
    assert C.find_gaps([5000]) == []


# ---------------------------------------------------------------------------
# The leading gap (outages that span a file boundary)
# ---------------------------------------------------------------------------

def test_late_start_counts_as_a_restart():
    """An outage running across midnight leaves no interior gap in either day's
    file -- the first just ends early, the second just starts late -- so without
    the window start it would go uncounted entirely."""
    times = _times((_HOUR, 10))            # first sample an hour into the window
    assert C.find_gaps(times) == []
    assert C.find_gaps(times, window_start_ms=0) == [(0, _HOUR)]


def test_on_time_start_is_not_a_restart():
    times = _times((0, 10))
    assert C.find_gaps(times, window_start_ms=0) == []


def test_leading_gap_does_not_split_blocks():
    """A late start is a restart relative to the expected window, but the
    samples that are present are still one uninterrupted run."""
    times = _times((_HOUR, 10))
    assert len(C.continuous_blocks(times)) == 1


# ---------------------------------------------------------------------------
# Per-bin attribution
# ---------------------------------------------------------------------------

def _comp(times: list[int], **kw) -> pa.Table:
    table = pa.table({"time": pa.array(times, type=pa.int64())})
    return C.compute_completeness(table, **kw)


def test_restart_is_attributed_to_the_bin_where_data_resumed():
    """A multi-bin outage counts once, in the bin that got data back -- the bins
    it spans are empty, which `completeness` already reports."""
    bin_ms = 15 * 60 * 1000
    times = _times((0, 60), (3 * bin_ms + 1000, 60))
    out = _comp(times)
    counts = out.column("restart_count").to_pylist()
    assert counts[0] == 0            # the bin where it stopped
    assert counts[1] == 0            # spanned, empty
    assert counts[2] == 0
    assert counts[3] == 1            # the bin where it came back
    assert sum(counts) == 1


def test_bin_counts_sum_to_the_total_gap_count():
    """The property the heatmap relies on when it coarsens 15-min bins."""
    times = _times((0, 60), (600_000, 60), (2_000_000, 60), (5_000_000, 60))
    out = _comp(times)
    assert sum(out.column("restart_count").to_pylist()) == len(C.find_gaps(times))


def test_max_gap_is_recorded_per_bin():
    times = _times((0, 10), (100_000, 10))
    out = _comp(times)
    gaps = [g for g in out.column("max_gap_s").to_pylist() if g is not None]
    assert gaps == [pytest.approx((100_000 - 9_000) / 1000.0)]


def test_bins_without_a_restart_record_a_null_max_gap():
    out = _comp(_times((0, 900)))
    assert out.column("max_gap_s").to_pylist() == [None]
    assert out.column("restart_count").to_pylist() == [0]


def test_gap_seconds_is_recorded_in_the_table():
    out = _comp(_times((0, 10)), gap_seconds=7.5)
    assert C.read_gap_seconds(out) == 7.5


def test_empty_table_still_carries_the_schema_and_threshold():
    out = C.compute_completeness(pa.table({"time": pa.array([], type=pa.int64())}))
    assert set(C._REQUIRED_COLUMNS).issubset(set(out.schema.names))
    assert C.read_gap_seconds(out) == C._GAP_SECONDS


# ---------------------------------------------------------------------------
# File-level: window parsing and regeneration of pre-gap-tracking files
# ---------------------------------------------------------------------------

def test_window_start_parsed_from_the_filename():
    p = pathlib.Path("P143.NC.LY_.20_20260115T000000Z_20260116T000000Z.arrow")
    assert C.window_start_ms(p) == 1768435200000


def test_window_start_none_for_an_unrecognised_name():
    assert C.window_start_ms(pathlib.Path("something-else.arrow")) is None


def _write_source(tmp_path: pathlib.Path) -> pathlib.Path:
    d = tmp_path / "P143.NC.LY_.20" / "202601"
    d.mkdir(parents=True)
    p = d / "P143.NC.LY_.20_20260115T000000Z_20260116T000000Z.arrow"
    p.write_bytes(make_positions_arrow(120, as_stream=True))
    return p


def test_generated_file_has_the_gap_columns(tmp_path):
    src = _write_source(tmp_path)
    out = C.generate_completeness_file(src)
    assert out is not None
    table = ipc.open_stream(out).read_all()
    assert set(C._REQUIRED_COLUMNS).issubset(set(table.schema.names))
    assert not C.is_stale(out)


def test_a_current_file_is_not_regenerated(tmp_path):
    src = _write_source(tmp_path)
    C.generate_completeness_file(src)
    assert C.generate_completeness_file(src) is None


def test_a_file_predating_gap_tracking_is_regenerated(tmp_path):
    """Served as-is it would have no restart_count at all, and the metric would
    read as a uniform zero -- indistinguishable from a stream with no outages."""
    src = _write_source(tmp_path)
    out = C.completeness_path(src)
    legacy = C.compute_completeness(
        pa.table({"time": pa.array([0, 1000], type=pa.int64())})
    ).drop_columns(list(C._REQUIRED_COLUMNS))
    C._write_stream(legacy, out)

    assert C.is_stale(out)
    assert C.generate_completeness_file(src) == out      # regenerated despite existing
    assert not C.is_stale(out)


def test_derived_arrow_files_are_not_treated_as_sources(tmp_path):
    """Both live beside their source, so a plain rglob("*.arrow") finds them.
    A PPSD file has no `time` column and used to abort the whole walk."""
    src = _write_source(tmp_path)
    assert C.is_source_arrow(src)
    assert not C.is_source_arrow(C.completeness_path(src))
    assert not C.is_source_arrow(src.parent / "P143.NC.LY_.20_ppsd.arrow")


def test_generate_all_skips_ppsd_files(tmp_path):
    src = _write_source(tmp_path)
    ppsd = src.parent / "P143.NC.LY_.20_202601_ppsd.arrow"
    C._write_stream(pa.table({"p_bin": pa.array([1], type=pa.int64())}), ppsd)

    written = C.generate_all(tmp_path)
    assert written == [C.completeness_path(src)]


def test_an_unreadable_completeness_file_is_stale(tmp_path):
    p = tmp_path / "broken.completeness.arrow"
    p.write_bytes(b"not arrow")
    assert C.is_stale(p)

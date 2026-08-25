"""Fetch progress accounting when cache hits are filtered out upstream.

The web UI computes which (stream, day) pairs are missing and hands only those
to the fetch subprocess. Without carrying the excluded count forward, a mostly
cached run displays as a small fresh download with `cached: 0`, which reads as
the cache not working at all.
"""
from __future__ import annotations

import datetime as dt

import pytest

from earthscope_positions.fetch.positions_fetch import _Progress

DAY = dt.date(2026, 1, 15)


def test_precached_counts_toward_the_total():
    p = _Progress(total=8, precached=92)
    assert p.total == 100
    assert p.cached == 92
    assert p.done == 92, "cache hits are already accounted for before any work"


def test_progress_reaches_the_full_total():
    p = _Progress(total=8, precached=92)
    for _ in range(8):
        p.update("ok", "P143.PB.LY_.10", DAY)
    assert p.done == p.total == 100
    assert p.ok == 8 and p.cached == 92


def test_without_precached_nothing_changes():
    """The CLI path has no upstream filter and must be unaffected."""
    p = _Progress(total=8)
    assert (p.total, p.cached, p.done) == (8, 0, 0)


def test_precached_appears_in_the_summary():
    p = _Progress(total=2, precached=98)
    p.update("ok", "P143.PB.LY_.10", DAY)
    p.update("no-data", "P157.NC.LY_.20", DAY)
    summary = p.summary()
    assert "98 cached" in summary
    assert "1 downloaded" in summary
    assert "1 no-data" in summary


def test_in_process_cache_hits_add_to_the_seeded_count():
    """A pair the subprocess itself finds cached joins the same bucket."""
    p = _Progress(total=3, precached=10)
    p.update("skipped", "P143.PB.LY_.10", DAY)
    assert p.cached == 11
    assert p.done == 11


def test_fully_cached_run_is_already_complete():
    p = _Progress(total=0, precached=250)
    assert p.done == p.total == 250
    assert p.cached == 250


def test_eta_does_not_divide_by_zero_when_everything_is_precached(capsys):
    """done > 0 from the start, so the ETA branch runs on the first render --
    with total == done the rate maths must not blow up."""
    p = _Progress(total=0, precached=5)
    p._render()
    assert "ETA" in capsys.readouterr().err


@pytest.mark.parametrize("precached", [0, 1, 5000])
def test_totals_stay_consistent(precached):
    p = _Progress(total=4, precached=precached)
    for status in ("ok", "skipped", "no-data", "error-503"):
        p.update(status, "P143.PB.LY_.10", DAY)
    assert p.done == p.total
    assert p.ok + p.cached + p.no_data + p.failed == precached + 4

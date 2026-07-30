"""Tests for the shared time-filtered-table cache (_load_filtered_table) used
by both /api/positions and /api/coherence."""
from __future__ import annotations

import asyncio
import datetime as dt
import pathlib

import pytest

from conftest import make_positions_arrow

_UTC = dt.timezone.utc
_GEOSNCL = "P100.NC.LY_.20"
_START = dt.datetime(2026, 1, 15, tzinfo=_UTC)
_END = dt.datetime(2026, 1, 16, tzinfo=_UTC)


def _write_arrow(data_dir: pathlib.Path, geosncl: str, n_rows: int = 3600) -> None:
    gsdir = data_dir / "arrow" / geosncl / "202601"
    gsdir.mkdir(parents=True, exist_ok=True)
    end = _START + dt.timedelta(seconds=n_rows)
    fname = f"{geosncl}_{_START.strftime('%Y%m%dT%H%M%SZ')}_{end.strftime('%Y%m%dT%H%M%SZ')}.arrow"
    (gsdir / fname).write_bytes(make_positions_arrow(n_rows, start=_START, as_stream=True))


@pytest.fixture
def w(project_tree):
    import earthscope_positions.webserver.webserver as w

    _write_arrow(project_tree / "data", _GEOSNCL)
    w._file_index = w._scan_data_dir_sync(w._data_dir())
    w._table_cache.clear()
    yield w
    w._table_cache.clear()


def test_second_call_is_served_from_cache(w):
    t1 = w._load_filtered_table(_GEOSNCL, _START, _END)
    t2 = w._load_filtered_table(_GEOSNCL, _START, _END)
    assert t1 is not None
    assert t2 is t1  # same object — no re-read/re-parse


def test_different_range_is_not_a_cache_hit(w):
    t1 = w._load_filtered_table(_GEOSNCL, _START, _END)
    other_end = _END + dt.timedelta(days=1)
    t2 = w._load_filtered_table(_GEOSNCL, _START, other_end)
    assert t2 is not t1


def test_expired_entry_is_reloaded(w):
    t1 = w._load_filtered_table(_GEOSNCL, _START, _END)
    start_ms = int(_START.timestamp() * 1000)
    end_ms = int(_END.timestamp() * 1000)
    key = (_GEOSNCL, start_ms, end_ms)

    with w._table_cache_lock:
        cached_at, table = w._table_cache[key]
        w._table_cache[key] = (cached_at - w._TABLE_CACHE_TTL_S - 1, table)

    t2 = w._load_filtered_table(_GEOSNCL, _START, _END)
    assert t2 is not t1              # re-read after expiry...
    assert t2.num_rows == t1.num_rows  # ...but with the same content


def test_clear_table_cache_empties_it(w):
    w._load_filtered_table(_GEOSNCL, _START, _END)
    assert len(w._table_cache) == 1
    w._clear_table_cache()
    assert len(w._table_cache) == 0


def test_refresh_index_clears_the_table_cache(w):
    w._load_filtered_table(_GEOSNCL, _START, _END)
    assert len(w._table_cache) == 1

    w._index_lock = asyncio.Lock()
    asyncio.run(w._refresh_index())
    assert len(w._table_cache) == 0


def test_cache_is_capped_at_max_entries(w):
    for i in range(w._TABLE_CACHE_MAX_ENTRIES + 5):
        end = _START + dt.timedelta(seconds=i + 1)
        w._load_filtered_table(_GEOSNCL, _START, end)
    assert len(w._table_cache) <= w._TABLE_CACHE_MAX_ENTRIES


def test_no_data_is_not_cached(w):
    other = "P999.NC.LY_.20"
    result = w._load_filtered_table(other, _START, _END)
    assert result is None
    assert (other, int(_START.timestamp() * 1000), int(_END.timestamp() * 1000)) not in w._table_cache

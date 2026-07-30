"""Regression tests for _geosncls_for_list — it must return every geosncl a
stream list *names*, not just the ones already downloaded/indexed locally.

Bug: a stream list containing both already-fetched streams and newly-added
(never-fetched) ones only surfaced the already-fetched subset in Fetch
Data's filter chips (/api/stream-lists/filter-options), the station tree
(/api/stations), and would have done the same to the Completeness page —
because _geosncls_for_list silently intersected list membership with the
local file index, defeating the entire point of those callers (finding out
what's fetchable / showing not-yet-fetched streams as gaps)."""
from __future__ import annotations

import datetime as dt
import json
import pathlib

import pytest

from conftest import make_positions_arrow

_UTC = dt.timezone.utc
_START = dt.datetime(2026, 1, 15, tzinfo=_UTC)


def _write_arrow(data_dir: pathlib.Path, geosncl: str, n_rows: int = 100) -> None:
    gsdir = data_dir / "arrow" / geosncl / "202601"
    gsdir.mkdir(parents=True, exist_ok=True)
    end = _START + dt.timedelta(seconds=n_rows)
    fname = f"{geosncl}_{_START.strftime('%Y%m%dT%H%M%SZ')}_{end.strftime('%Y%m%dT%H%M%SZ')}.arrow"
    (gsdir / fname).write_bytes(make_positions_arrow(n_rows, start=_START, as_stream=True))


def _write_stream_list(data_dir: pathlib.Path, name: str, geosncls: list[str]) -> None:
    d = data_dir / "stream-lists"
    d.mkdir(parents=True, exist_ok=True)
    with open(d / f"{name}.jsonl", "w") as f:
        for g in geosncls:
            f.write(json.dumps({"geosncl": g}) + "\n")


@pytest.fixture
def mixed_client(project_tree):
    """A stream list naming 4 streams — only 2 of which have been downloaded —
    mirroring the reported scenario (list expanded to add streams beyond an
    originally-downloaded 00/30/40 subset)."""
    from fastapi.testclient import TestClient
    import earthscope_positions.webserver.webserver as w

    data_dir = project_tree / "data"
    _write_arrow(data_dir, "ALDR.PW.LY_.00")
    _write_arrow(data_dir, "BRI2.PW.LY_.30")
    _write_stream_list(data_dir, "mixed", [
        "ALDR.PW.LY_.00",   # downloaded
        "BRI2.PW.LY_.30",   # downloaded
        "CMBB.PB.LY_.40",   # never downloaded
        "DIXN.PB.LY_.50",   # never downloaded, sol_type "50" doesn't exist on disk anywhere
    ])
    w._file_index = w._scan_data_dir_sync(w._data_dir())
    # Completeness generation needs _gen_locks_mu, which is only initialized
    # by the startup event — entering the TestClient context triggers it.
    with TestClient(w.app) as client:
        yield client


def test_geosncls_for_list_includes_never_downloaded_streams(mixed_client):
    import earthscope_positions.webserver.webserver as w
    geosncls = w._geosncls_for_list("mixed")
    assert geosncls == [
        "ALDR.PW.LY_.00", "BRI2.PW.LY_.30", "CMBB.PB.LY_.40", "DIXN.PB.LY_.50",
    ]


def test_filter_options_reflects_full_list_not_just_downloaded(mixed_client):
    r = mixed_client.get("/api/stream-lists/filter-options", params={"lists": ["mixed"]})
    assert r.status_code == 200
    body = r.json()
    assert body["centers"] == ["PB", "PW"]
    # "40" and "50" only exist on the never-downloaded streams — they must
    # still show up so Fetch Data can offer them as selectable stream types.
    assert body["sol_types"] == ["00", "30", "40", "50"]


def test_stations_endpoint_lists_never_downloaded_streams(mixed_client):
    r = mixed_client.get("/api/stations", params={"list": "mixed"})
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 4
    geosncls = {s["geosncl"] for s in body["stations"]}
    assert geosncls == {
        "ALDR.PW.LY_.00", "BRI2.PW.LY_.30", "CMBB.PB.LY_.40", "DIXN.PB.LY_.50",
    }


def test_completeness_includes_never_downloaded_streams(mixed_client):
    r = mixed_client.get("/api/completeness", params={
        "list": "mixed", "search": "", "start": "2026-01-15", "end": "2026-01-16",
        "page": 0, "size": 50,
    })
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 4
    geosncls = {s["geosncl"] for s in body["stations"]}
    assert "CMBB.PB.LY_.40" in geosncls
    assert "DIXN.PB.LY_.50" in geosncls


def test_all_list_still_includes_indexed_streams_not_in_any_saved_list(project_tree):
    """The 'all' pseudo-list must still surface streams that only exist on
    disk (indexed) and aren't named in any saved stream-list file — the
    union behavior already used by /api/station-builder/data."""
    import earthscope_positions.webserver.webserver as w

    data_dir = project_tree / "data"
    _write_arrow(data_dir, "ORPHAN.CI.LY_.60")  # downloaded, but in no saved list
    _write_stream_list(data_dir, "some_list", ["NAMED.PB.LY_.10"])  # named, never downloaded
    w._file_index = w._scan_data_dir_sync(w._data_dir())

    geosncls = w._geosncls_for_list("all")
    assert "ORPHAN.CI.LY_.60" in geosncls
    assert "NAMED.PB.LY_.10" in geosncls

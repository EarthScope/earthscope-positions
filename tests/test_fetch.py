"""Tests for position-data download — the REST API is spoofed with `responses`.

``positions_fetch`` calls ``requests.get(_API_BASE, ...)`` directly, so every
test here registers a canned reply on the ``mock_positions_api`` fixture; any
un-registered request would raise, guaranteeing no real network access.
"""
from __future__ import annotations

import datetime as dt

import orjson
import pytest

from earthscope_positions.fetch import positions_fetch
from conftest import make_positions_arrow

_UTC = dt.timezone.utc
_GEOSNCL = "P123.CI.LY_.20"
_EDID = "01ABCDEF0123456789ABCDEFGH"


def _day():
    start = dt.datetime(2026, 1, 15, tzinfo=_UTC)
    return start, start + dt.timedelta(days=1)


def _register(rsps, **kwargs):
    """Register one reply for the positions endpoint."""
    rsps.get(positions_fetch._API_BASE, **kwargs)


# ---------------------------------------------------------------------------
# _fetch_one_day — the single unit that makes an API call
# ---------------------------------------------------------------------------


def test_fetch_ok_writes_arrow_file(project_tree, mock_positions_api):
    day_start, day_end = _day()
    _register(
        mock_positions_api,
        body=make_positions_arrow(50),
        status=200,
        content_type="application/vnd.apache.arrow.stream",
    )

    status = positions_fetch._fetch_one_day(
        "test-token", _EDID, _GEOSNCL, day_start, day_end,
        force=False, redownload=False,
    )

    assert status == "ok"
    out = positions_fetch._arrow_path(
        positions_fetch._geosncl_dir(_GEOSNCL), day_start, day_end
    )
    assert out.exists()
    tbl = positions_fetch._read_arrow_bytes(out.read_bytes())
    assert tbl is not None and tbl.num_rows == 50


def test_fetch_sends_expected_request(project_tree, mock_positions_api):
    day_start, day_end = _day()
    _register(mock_positions_api, body=make_positions_arrow(1), status=200)

    positions_fetch._fetch_one_day(
        "secret-token", _EDID, _GEOSNCL, day_start, day_end,
        force=False, redownload=False,
    )

    req = mock_positions_api.calls[0].request
    assert f"stream_id={_EDID}" in req.url
    assert "start_datetime=2026-01-15" in req.url
    assert req.headers["authorization"] == "Bearer secret-token"


def test_fetch_stream_format_decodes(project_tree, mock_positions_api):
    """The endpoint sends Arrow *stream* format; decode path must handle it."""
    day_start, day_end = _day()
    _register(mock_positions_api, body=make_positions_arrow(5, as_stream=True), status=200)

    status = positions_fetch._fetch_one_day(
        "test-token", _EDID, _GEOSNCL, day_start, day_end,
        force=False, redownload=False,
    )
    assert status == "ok"


def test_fetch_200_empty_body_is_no_data(project_tree, mock_positions_api):
    day_start, day_end = _day()
    _register(mock_positions_api, body=b"", status=200)

    status = positions_fetch._fetch_one_day(
        "test-token", _EDID, _GEOSNCL, day_start, day_end,
        force=False, redownload=False,
    )

    assert status == "no-data"
    # A no-data marker should now suppress the date.
    gdir = positions_fetch._geosncl_dir(_GEOSNCL)
    assert "2026-01-15" in positions_fetch._load_no_data(gdir)


def test_fetch_404_is_no_data(project_tree, mock_positions_api):
    day_start, day_end = _day()
    _register(mock_positions_api, json={"detail": "not found"}, status=404)

    status = positions_fetch._fetch_one_day(
        "test-token", _EDID, _GEOSNCL, day_start, day_end,
        force=False, redownload=False,
    )
    assert status == "no-data"


def test_fetch_422_records_error_marker(project_tree, mock_positions_api):
    day_start, day_end = _day()
    _register(mock_positions_api, json={"detail": "bad request"}, status=422)

    status = positions_fetch._fetch_one_day(
        "test-token", _EDID, _GEOSNCL, day_start, day_end,
        force=False, redownload=False,
    )

    # Returns "no-data" (won't retry automatically) but marker records the error
    assert status == "no-data"
    gdir = positions_fetch._geosncl_dir(_GEOSNCL)
    marker = gdir / positions_fetch._NO_DATA_FILE
    rec = orjson.loads(marker.read_text().splitlines()[-1])
    assert rec["result"] == "error-422"
    # error-* markers are NOT treated as permanent no-data
    assert "2026-01-15" not in positions_fetch._load_no_data(gdir)


def test_fetch_500_is_retryable_error(project_tree, mock_positions_api):
    day_start, day_end = _day()
    _register(mock_positions_api, json={"detail": "boom"}, status=503)

    status = positions_fetch._fetch_one_day(
        "test-token", _EDID, _GEOSNCL, day_start, day_end,
        force=False, redownload=False,
    )
    assert status == "error-503"


def test_fetch_skips_when_file_exists(project_tree, mock_positions_api):
    """Second fetch is served from cache — no API call registered, none made."""
    day_start, day_end = _day()
    _register(mock_positions_api, body=make_positions_arrow(3), status=200)

    first = positions_fetch._fetch_one_day(
        "test-token", _EDID, _GEOSNCL, day_start, day_end,
        force=False, redownload=False,
    )
    assert first == "ok"

    second = positions_fetch._fetch_one_day(
        "test-token", _EDID, _GEOSNCL, day_start, day_end,
        force=False, redownload=False,
    )
    assert second == "skipped"
    assert len(mock_positions_api.calls) == 1  # only the first hit the API


def test_no_data_cached_skips_api(project_tree, mock_positions_api):
    """A cached no-data date is skipped without an API call."""
    day_start, day_end = _day()
    gdir = positions_fetch._geosncl_dir(_GEOSNCL)
    positions_fetch._add_no_data(gdir, "2026-01-15", "no-data")

    status = positions_fetch._fetch_one_day(
        "test-token", _EDID, _GEOSNCL, day_start, day_end,
        force=False, redownload=False,
    )
    assert status == "no-data-cached"
    assert len(mock_positions_api.calls) == 0


# ---------------------------------------------------------------------------
# _cmd_get — end-to-end through the CLI command layer
# ---------------------------------------------------------------------------


def test_cmd_get_end_to_end(project_tree, fake_token, mock_positions_api):
    # A station list file the command will read.
    sl = project_tree / "data" / "station-lists" / "mylist.jsonl"
    sl.write_bytes(orjson.dumps({"geosncl": _GEOSNCL, "edid": _EDID}) + b"\n")

    _register(mock_positions_api, body=make_positions_arrow(20), status=200)

    args = _Namespace(
        input=[str(sl)],
        start="2026-01-15",
        end="2026-01-16",
        force=False,
        redownload=False,
        workers=1,
    )
    positions_fetch._cmd_get(args)

    out = positions_fetch._arrow_path(
        positions_fetch._geosncl_dir(_GEOSNCL),
        dt.datetime(2026, 1, 15, tzinfo=_UTC),
        dt.datetime(2026, 1, 16, tzinfo=_UTC),
    )
    assert out.exists()
    assert len(mock_positions_api.calls) == 1


class _Namespace:
    """Minimal argparse.Namespace stand-in."""

    def __init__(self, **kw):
        self.__dict__.update(kw)

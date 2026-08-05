"""Tests for position-data download — the EarthScope SDK's async client is
spoofed with a minimal fake (_FakeClient), since positions_fetch now calls
AsyncEarthScopeClient.data._get_gnss_instantaneous_positions directly rather
than making its own HTTP requests.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import io
import sys
from unittest.mock import AsyncMock

import httpx
import orjson
import pyarrow as pa
import pytest
from earthscope_sdk.auth.error import UnauthenticatedError

from earthscope_positions.fetch import positions_fetch
from conftest import make_positions_arrow

_UTC = dt.timezone.utc
_GEOSNCL = "P123.CI.LY_.20"
_EDID = "01ABCDEF0123456789ABCDEFGH"
_POSITIONS_URL = "https://api.earthscope.org/beta/data-products/gnss/positions/instantaneous/v2"


def _day():
    start = dt.datetime(2026, 1, 15, tzinfo=_UTC)
    return start, start + dt.timedelta(days=1)


def _positions_table(n_rows: int, edid: str = _EDID) -> pa.Table:
    """Build a table shaped like what the SDK actually returns: the raw
    position rows plus an "edid" column (added by its load_table_with_extra —
    see _fetch_one_day, which must drop that column again before writing)."""
    raw = make_positions_arrow(n_rows, as_stream=True)
    tbl = pa.ipc.open_stream(io.BytesIO(raw)).read_all()
    return tbl.append_column("edid", pa.array([edid] * n_rows, type=pa.string()))


def _http_status_error(status_code: int, detail: str = "") -> httpx.HTTPStatusError:
    request = httpx.Request("GET", _POSITIONS_URL)
    response = httpx.Response(
        status_code,
        json={"detail": detail} if detail else None,
        request=request,
    )
    return httpx.HTTPStatusError(f"{status_code} error", request=request, response=response)


class _FakeDataAccess:
    def __init__(self):
        self._get_gnss_instantaneous_positions = AsyncMock()


class _FakeClient:
    """Stand-in for AsyncEarthScopeClient: supports `async with` and exposes
    `.data._get_gnss_instantaneous_positions` as a configurable AsyncMock —
    set `.return_value` to a pyarrow.Table, or `.side_effect` to an exception,
    per test."""

    def __init__(self):
        self.data = _FakeDataAccess()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False


# ---------------------------------------------------------------------------
# _fetch_one_day — the single unit that calls the SDK
# ---------------------------------------------------------------------------


def test_fetch_ok_writes_arrow_file(project_tree):
    day_start, day_end = _day()
    client = _FakeClient()
    client.data._get_gnss_instantaneous_positions.return_value = _positions_table(50)

    status = asyncio.run(positions_fetch._fetch_one_day(
        client, _EDID, _GEOSNCL, day_start, day_end, force=False, redownload=False,
    ))

    assert status == "ok"
    out = positions_fetch._arrow_path(
        positions_fetch._geosncl_dir(_GEOSNCL), day_start, day_end
    )
    assert out.exists()
    tbl = positions_fetch._read_arrow_bytes(out.read_bytes())
    assert tbl is not None and tbl.num_rows == 50
    # The SDK's added "edid" column must not leak into the on-disk schema.
    assert "edid" not in tbl.schema.names


def test_fetch_calls_sdk_with_expected_args(project_tree):
    day_start, day_end = _day()
    client = _FakeClient()
    client.data._get_gnss_instantaneous_positions.return_value = _positions_table(1)

    asyncio.run(positions_fetch._fetch_one_day(
        client, _EDID, _GEOSNCL, day_start, day_end, force=False, redownload=False,
    ))

    client.data._get_gnss_instantaneous_positions.assert_awaited_once_with(
        stream_edid=_EDID, start_datetime=day_start, end_datetime=day_end,
    )


def test_fetch_200_empty_body_is_no_data(project_tree):
    day_start, day_end = _day()
    client = _FakeClient()
    client.data._get_gnss_instantaneous_positions.return_value = _positions_table(0)

    status = asyncio.run(positions_fetch._fetch_one_day(
        client, _EDID, _GEOSNCL, day_start, day_end, force=False, redownload=False,
    ))

    assert status == "no-data"
    # A no-data marker should now suppress the date.
    gdir = positions_fetch._geosncl_dir(_GEOSNCL)
    assert "2026-01-15" in positions_fetch._load_no_data(gdir)


def test_fetch_404_is_no_data(project_tree):
    day_start, day_end = _day()
    client = _FakeClient()
    client.data._get_gnss_instantaneous_positions.side_effect = _http_status_error(404, "not found")

    status = asyncio.run(positions_fetch._fetch_one_day(
        client, _EDID, _GEOSNCL, day_start, day_end, force=False, redownload=False,
    ))
    assert status == "no-data"


def test_fetch_422_records_error_marker(project_tree):
    day_start, day_end = _day()
    client = _FakeClient()
    client.data._get_gnss_instantaneous_positions.side_effect = _http_status_error(422, "bad request")

    status = asyncio.run(positions_fetch._fetch_one_day(
        client, _EDID, _GEOSNCL, day_start, day_end, force=False, redownload=False,
    ))

    # Returns "rejected-422" — distinct from "no-data" so a malformed request
    # (e.g. a stream list missing edid) stays visible instead of reading as
    # an absence of data — but won't retry automatically, and the marker
    # still records the error.
    assert status == "rejected-422"
    gdir = positions_fetch._geosncl_dir(_GEOSNCL)
    marker = gdir / positions_fetch._NO_DATA_FILE
    rec = orjson.loads(marker.read_text().splitlines()[-1])
    assert rec["result"] == "error-422"
    # error-* markers are NOT treated as permanent no-data
    assert "2026-01-15" not in positions_fetch._load_no_data(gdir)


def test_fetch_500_is_retryable_error(project_tree):
    day_start, day_end = _day()
    client = _FakeClient()
    client.data._get_gnss_instantaneous_positions.side_effect = _http_status_error(503, "boom")

    status = asyncio.run(positions_fetch._fetch_one_day(
        client, _EDID, _GEOSNCL, day_start, day_end, force=False, redownload=False,
    ))
    assert status == "error-503"


def test_auth_failure_exits_process(project_tree):
    """UnauthenticatedError means the SDK's own refresh failed — every other
    request this run would fail identically, so this is fatal, not retryable."""
    day_start, day_end = _day()
    client = _FakeClient()
    client.data._get_gnss_instantaneous_positions.side_effect = UnauthenticatedError("expired")

    with pytest.raises(SystemExit):
        asyncio.run(positions_fetch._fetch_one_day(
            client, _EDID, _GEOSNCL, day_start, day_end, force=False, redownload=False,
        ))


def test_fetch_skips_when_file_exists(project_tree):
    """Second fetch is served from cache — the SDK is called only once."""
    day_start, day_end = _day()
    client = _FakeClient()
    client.data._get_gnss_instantaneous_positions.return_value = _positions_table(3)

    first = asyncio.run(positions_fetch._fetch_one_day(
        client, _EDID, _GEOSNCL, day_start, day_end, force=False, redownload=False,
    ))
    assert first == "ok"

    second = asyncio.run(positions_fetch._fetch_one_day(
        client, _EDID, _GEOSNCL, day_start, day_end, force=False, redownload=False,
    ))
    assert second == "skipped"
    assert client.data._get_gnss_instantaneous_positions.await_count == 1


def test_no_data_cached_skips_api(project_tree):
    """A cached no-data date is skipped without calling the SDK."""
    day_start, day_end = _day()
    gdir = positions_fetch._geosncl_dir(_GEOSNCL)
    positions_fetch._add_no_data(gdir, "2026-01-15", "no-data")

    client = _FakeClient()
    status = asyncio.run(positions_fetch._fetch_one_day(
        client, _EDID, _GEOSNCL, day_start, day_end, force=False, redownload=False,
    ))
    assert status == "no-data-cached"
    client.data._get_gnss_instantaneous_positions.assert_not_awaited()


# ---------------------------------------------------------------------------
# _run_parallel — the outer retry net for transient failures the SDK's own
# internal retries didn't resolve.
# ---------------------------------------------------------------------------


def test_run_parallel_retries_transient_errors(project_tree):
    day_start, day_end = _day()
    client = _FakeClient()
    client.data._get_gnss_instantaneous_positions.side_effect = [
        _http_status_error(503, "boom"),
        _positions_table(10),
    ]

    progress = positions_fetch._Progress(1)
    task = (_EDID, _GEOSNCL, day_start, day_end, False, False, positions_fetch._MAX_RETRIES)
    asyncio.run(positions_fetch._run_parallel([task], 1, progress, client))

    assert progress.ok == 1
    assert progress.failed == 0
    assert client.data._get_gnss_instantaneous_positions.await_count == 2


# ---------------------------------------------------------------------------
# _cmd_get — end-to-end through the CLI command layer
# ---------------------------------------------------------------------------


def test_cmd_get_end_to_end(project_tree, monkeypatch):
    # A station list file the command will read.
    sl = project_tree / "data" / "stream-lists" / "mylist.jsonl"
    sl.write_bytes(orjson.dumps({"geosncl": _GEOSNCL, "edid": _EDID}) + b"\n")

    client = _FakeClient()
    client.data._get_gnss_instantaneous_positions.return_value = _positions_table(20)
    monkeypatch.setattr(positions_fetch, "_make_client", lambda: client)

    args = _Namespace(
        list=[str(sl)],
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
    assert client.data._get_gnss_instantaneous_positions.await_count == 1


def test_cmd_get_backfills_missing_edid(project_tree, monkeypatch):
    """A stream list saved with only {"geosncl": ...} (no edid — e.g. from a
    web-UI-built list, before the fix to api_save_stream_list) must not send
    the geosncl string as stream_id: it 422s on the real API. _cmd_get should
    backfill the real edid from any other stream-list file that has it."""
    # The broken list: geosncl only, no edid.
    broken = project_tree / "data" / "stream-lists" / "SCGN-ALL.jsonl"
    broken.write_bytes(orjson.dumps({"geosncl": _GEOSNCL}) + b"\n")
    # A separate, already-correct list (mirrors all-streams.jsonl) providing
    # the real edid for the same geosncl.
    reference = project_tree / "data" / "stream-lists" / "all-streams.jsonl"
    reference.write_bytes(orjson.dumps({"geosncl": _GEOSNCL, "edid": _EDID}) + b"\n")

    client = _FakeClient()
    client.data._get_gnss_instantaneous_positions.return_value = _positions_table(20)
    monkeypatch.setattr(positions_fetch, "_make_client", lambda: client)

    args = _Namespace(
        list=[str(broken)],
        start="2026-01-15",
        end="2026-01-16",
        force=False,
        redownload=False,
        workers=1,
    )
    positions_fetch._cmd_get(args)

    # The SDK must have been called with the real EDID, not the geosncl string.
    client.data._get_gnss_instantaneous_positions.assert_awaited_once_with(
        stream_edid=_EDID,
        start_datetime=dt.datetime(2026, 1, 15, tzinfo=_UTC),
        end_datetime=dt.datetime(2026, 1, 16, tzinfo=_UTC),
    )


class _Namespace:
    """Minimal argparse.Namespace stand-in."""

    def __init__(self, **kw):
        self.__dict__.update(kw)


# ---------------------------------------------------------------------------
# CLI parser — one flat command (no get/retry/concat subcommands), --list
# instead of -i/--input, --retry instead of a "retry" subcommand.
# ---------------------------------------------------------------------------


def test_parser_list_mode_defaults():
    ap = positions_fetch._build_parser()
    args = ap.parse_args(["--list", "ShakeAlert", "--start", "2026-01-01"])
    assert args.list == ["ShakeAlert"]
    assert args.retry is False
    assert args.workers == positions_fetch._DEFAULT_WORKERS


def test_parser_list_can_repeat():
    ap = positions_fetch._build_parser()
    args = ap.parse_args(["--list", "a", "--list", "b"])
    assert args.list == ["a", "b"]


def test_parser_retry_mode():
    ap = positions_fetch._build_parser()
    args = ap.parse_args(["--retry", "--result", "error-422", "--dry-run"])
    assert args.retry is True
    assert args.result == "error-422"
    assert args.dry_run is True
    assert args.list is None


def test_parser_no_longer_has_concat_subcommand():
    ap = positions_fetch._build_parser()
    with pytest.raises(SystemExit):
        ap.parse_args(["concat", "foo.arrow", "-o", "out.arrow"])
    # The underlying code is kept around for later, just not CLI-exposed.
    assert hasattr(positions_fetch, "_cmd_concat")
    assert hasattr(positions_fetch, "_concat_dedup")


def test_main_requires_list_or_retry(project_tree, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["es-pos-fetch"])
    with pytest.raises(SystemExit) as exc:
        positions_fetch.main()
    assert exc.value.code == 2


def test_main_dispatches_to_retry(project_tree, monkeypatch):
    called = {}
    monkeypatch.setattr(sys, "argv", ["es-pos-fetch", "--retry", "--dry-run"])
    monkeypatch.setattr(positions_fetch, "_cmd_retry", lambda args: called.setdefault("retry", args))
    monkeypatch.setattr(positions_fetch, "_cmd_get", lambda args: called.setdefault("get", args))
    positions_fetch.main()
    assert "retry" in called and "get" not in called


def test_main_dispatches_to_get(project_tree, monkeypatch):
    called = {}
    monkeypatch.setattr(sys, "argv", ["es-pos-fetch", "--list", "ShakeAlert"])
    monkeypatch.setattr(positions_fetch, "_cmd_retry", lambda args: called.setdefault("retry", args))
    monkeypatch.setattr(positions_fetch, "_cmd_get", lambda args: called.setdefault("get", args))
    positions_fetch.main()
    assert "get" in called and "retry" not in called

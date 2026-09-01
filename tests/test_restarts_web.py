"""Restarts as the web layer serves them: the Completeness heatmap's third
plot, and the File Explorer's per-file continuity summary.

The client is entered as a context manager in each test rather than built by a
fixture, because the startup scan is what populates the file index — the source
files have to exist before the app starts, not after.
"""
from __future__ import annotations

import datetime as dt
import io
import pathlib

import pyarrow as pa
import pyarrow.ipc as ipc
import pytest
from fastapi.testclient import TestClient

from conftest import make_positions_arrow
from earthscope_positions import paths
from earthscope_positions.process import completeness as C

_GEOSNCL = "P143.NC.LY_.20"
_DAY = dt.datetime(2026, 1, 15, tzinfo=dt.timezone.utc)


@pytest.fixture
def w(project_tree):
    import earthscope_positions.webserver.webserver as mod
    mod._completeness_checked.clear()
    return mod


def _source_path() -> pathlib.Path:
    d = paths.arrow_dir() / _GEOSNCL / "202601"
    d.mkdir(parents=True, exist_ok=True)
    end = _DAY + dt.timedelta(days=1)
    return d / f"{_GEOSNCL}_{_DAY:%Y%m%dT%H%M%SZ}_{end:%Y%m%dT%H%M%SZ}.arrow"


def _write_continuous(n_rows: int = 600, offset_minutes: int = 0) -> pathlib.Path:
    """One source file covering the day, samples starting *offset* into it."""
    p = _source_path()
    p.write_bytes(make_positions_arrow(
        n_rows, start=_DAY + dt.timedelta(minutes=offset_minutes), as_stream=True))
    return p


def _write_with_gap(gap_minutes: int = 30, n_each: int = 60) -> pathlib.Path:
    """One source file whose samples stop and resume *gap_minutes* later."""
    merged = pa.concat_tables([
        ipc.open_stream(io.BytesIO(make_positions_arrow(
            n_each, start=_DAY, as_stream=True))).read_all(),
        ipc.open_stream(io.BytesIO(make_positions_arrow(
            n_each, start=_DAY + dt.timedelta(minutes=gap_minutes),
            as_stream=True))).read_all(),
    ])
    sink = pa.BufferOutputStream()
    with ipc.new_stream(sink, merged.schema) as writer:
        writer.write_table(merged)
    p = _source_path()
    p.write_bytes(sink.getvalue().to_pybytes())
    return p


def _completeness(client) -> dict:
    return client.get(
        "/api/completeness",
        params={"list": "all", "start": "2026-01-15", "end": "2026-01-16"},
    ).json()


def _summary(client, src: pathlib.Path) -> dict:
    return client.get(
        "/api/files/summary",
        params={"path": str(src.relative_to(paths.base_dir()))},
    ).json()


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------

def test_restarts_add_up_when_bins_are_coarsened(w):
    """Each gap is recorded once, in the bin that resumed, so coarsening must
    not double-count it."""
    times: list[int] = []
    for start, n in ((0, 60), (600_000, 60), (2_000_000, 60)):
        times.extend(start + i * 1000 for i in range(n))
    fine = C.compute_completeness(pa.table({"time": pa.array(times, type=pa.int64())}))

    agg = w._aggregate_bins(fine, 24 * 3600 * 1000)        # everything into one day
    assert len(agg) == 1
    only = next(iter(agg.values()))
    assert only["restarts"] == sum(fine.column("restart_count").to_pylist()) == 2
    assert only["restarts_known"] is True


def test_a_pre_gap_tracking_table_reports_unknown_not_zero(w):
    """The distinction the heatmap depends on: "not measured" must not paint the
    same as "no outages"."""
    legacy = C.compute_completeness(
        pa.table({"time": pa.array([0, 1000, 2000], type=pa.int64())})
    ).drop_columns(list(C._REQUIRED_COLUMNS))
    agg = w._aggregate_bins(legacy, 15 * 60 * 1000)
    assert next(iter(agg.values()))["restarts_known"] is False


# ---------------------------------------------------------------------------
# /api/completeness
# ---------------------------------------------------------------------------

def test_buckets_carry_restart_counts(w):
    _write_continuous()
    with TestClient(w.app) as client:
        body = _completeness(client)
    assert body["gapSeconds"] == C._GAP_SECONDS
    has_data = [b for b in body["stations"][0]["buckets"] if b["state"] == "has-data"]
    assert has_data
    for b in has_data:
        assert b["restartCount"] == 0        # never None for a freshly built file
    assert all(b["maxGapS"] is None for b in has_data)


def test_a_gap_in_the_source_shows_up_as_one_restart(w):
    _write_with_gap(gap_minutes=30, n_each=60)
    with TestClient(w.app) as client:
        buckets = _completeness(client)["stations"][0]["buckets"]
    assert sum(b["restartCount"] or 0 for b in buckets) == 1
    # 00:00:59 → 00:30:00
    assert max((b["maxGapS"] or 0) for b in buckets) == pytest.approx(1741, abs=2)


def test_a_late_starting_file_counts_a_restart(w):
    """An outage spanning midnight leaves no interior gap in either day; the
    window start is the only thing that makes it visible."""
    _write_continuous(n_rows=60, offset_minutes=90)
    with TestClient(w.app) as client:
        buckets = _completeness(client)["stations"][0]["buckets"]
    assert sum(b["restartCount"] or 0 for b in buckets) == 1


def test_stale_completeness_files_are_regenerated_on_request(w):
    """A tree built before restarts existed has completeness files without the
    columns; left alone the plot would read as a uniform zero forever."""
    src = _write_continuous()
    out = C.completeness_path(src)
    legacy = C.compute_completeness(
        pa.table({"time": pa.array([0, 1000], type=pa.int64())})
    ).drop_columns(list(C._REQUIRED_COLUMNS))
    C._write_stream(legacy, out)
    assert C.is_stale(out)

    with TestClient(w.app) as client:
        body = _completeness(client)
    assert not C.is_stale(out)
    assert body["gapSeconds"] == C._GAP_SECONDS


# ---------------------------------------------------------------------------
# File Explorer
# ---------------------------------------------------------------------------

def test_arrow_summary_reports_one_block_for_a_continuous_file(w):
    src = _write_continuous(n_rows=120)
    with TestClient(w.app) as client:
        body = _summary(client, src)
    labels = dict(body["rows"])
    assert labels["Continuous blocks"] == "1"
    assert labels[f"Restarts (gap > {C._GAP_SECONDS:g} s)"] == "0"
    assert "Longest gap" not in labels          # nothing to report
    assert body["blocks_total"] == 1
    assert body["blocks"][0]["samples"] == 120


def test_arrow_summary_splits_blocks_on_a_gap(w):
    src = _write_with_gap(gap_minutes=30, n_each=60)
    with TestClient(w.app) as client:
        body = _summary(client, src)
    labels = dict(body["rows"])
    assert labels["Continuous blocks"] == "2"
    assert labels[f"Restarts (gap > {C._GAP_SECONDS:g} s)"] == "1"
    assert "Longest gap" in labels
    assert "Total time in gaps" in labels
    assert body["blocks_total"] == 2
    assert [b["samples"] for b in body["blocks"]] == [60, 60]


def test_arrow_summary_follows_the_threshold_the_data_was_built_with(w):
    """Otherwise a tree generated with an explicit --gap-seconds would show one
    threshold in the heatmap and the default in the per-file summary."""
    src = _write_with_gap(gap_minutes=30, n_each=60)
    C.generate_completeness_file(src, overwrite=True, gap_seconds=3600.0)

    with TestClient(w.app) as client:
        body = _summary(client, src)
    labels = dict(body["rows"])
    assert "Restarts (gap > 3600 s)" in labels
    assert labels["Restarts (gap > 3600 s)"] == "0"    # the 29-min gap is under it
    assert labels["Continuous blocks"] == "1"


def test_arrow_summary_counts_a_late_start_without_splitting_blocks(w):
    """Restarts and blocks-1 legitimately differ by one here: the stream came
    back late, but the samples it did deliver are one uninterrupted run."""
    src = _write_continuous(n_rows=60, offset_minutes=90)
    with TestClient(w.app) as client:
        body = _summary(client, src)
    labels = dict(body["rows"])
    assert labels["Continuous blocks"] == "1"
    assert labels[f"Restarts (gap > {C._GAP_SECONDS:g} s)"] == "1"


# ---------------------------------------------------------------------------
# Precache
# ---------------------------------------------------------------------------

def _sse_events(text: str) -> list[dict]:
    import json
    return [
        json.loads(line[6:])
        for block in text.split("\n\n")
        for line in block.split("\n")
        if line.startswith("data: ")
    ]


def test_precache_builds_every_file_in_the_selection(w):
    """The point of the button: cover the pages that are NOT on screen, so
    paging through afterwards needs no work."""
    for day in ("20260115", "20260116", "20260117"):
        d = paths.arrow_dir() / _GEOSNCL / "202601"
        d.mkdir(parents=True, exist_ok=True)
        start = dt.datetime.strptime(day, "%Y%m%d").replace(tzinfo=dt.timezone.utc)
        end = start + dt.timedelta(days=1)
        (d / f"{_GEOSNCL}_{start:%Y%m%dT%H%M%SZ}_{end:%Y%m%dT%H%M%SZ}.arrow").write_bytes(
            make_positions_arrow(60, start=start, as_stream=True))

    with TestClient(w.app) as client:
        r = client.post("/api/completeness/precache", json={
            "lists": ["all"], "start": "2026-01-15", "end": "2026-01-18"})
        events = _sse_events(r.text)

    done = [e for e in events if e["type"] == "done"][-1]
    assert done["total"] == 3
    assert done["generated"] == 3
    assert done["failed"] == 0
    assert len(list((paths.arrow_dir()).rglob("*.completeness.arrow"))) == 3


def test_precache_is_cheap_the_second_time(w):
    _write_continuous()
    with TestClient(w.app) as client:
        body = {"lists": ["all"], "start": "2026-01-15", "end": "2026-01-16"}
        first = _sse_events(client.post("/api/completeness/precache", json=body).text)
        second = _sse_events(client.post("/api/completeness/precache", json=body).text)
    assert [e for e in first if e["type"] == "done"][-1]["generated"] == 1
    assert [e for e in second if e["type"] == "done"][-1]["total"] == 0


def test_precache_rejects_a_bad_range(w):
    with TestClient(w.app) as client:
        events = _sse_events(client.post("/api/completeness/precache", json={
            "lists": ["all"], "start": "2026-01-16", "end": "2026-01-15"}).text)
    assert any(e["type"] == "error" for e in events)
    assert [e for e in events if e["type"] == "done"][-1]["code"] == 1


def test_precache_reports_an_unreadable_file_without_failing(w):
    src = _write_continuous()
    src.write_bytes(b"truncated garbage")
    with TestClient(w.app) as client:
        events = _sse_events(client.post("/api/completeness/precache", json={
            "lists": ["all"], "start": "2026-01-15", "end": "2026-01-16"}).text)
    done = [e for e in events if e["type"] == "done"][-1]
    assert done["failed"] == 1
    assert any(e["type"] == "error" for e in events)


# ---------------------------------------------------------------------------
# Damaged sources must not take the page down
# ---------------------------------------------------------------------------

def test_an_unreadable_source_is_reported_not_fatal(w):
    """Real trees contain truncated downloads; one used to make the gather()
    raise and 500 the whole Completeness page."""
    src = _write_continuous()
    src.write_bytes(b"truncated garbage")
    with TestClient(w.app) as client:
        r = client.get("/api/completeness", params={
            "list": "all", "start": "2026-01-15", "end": "2026-01-16"})
    assert r.status_code == 200
    body = r.json()
    assert body["damaged"]["count"] == 1
    assert body["damaged"]["files"][0]["name"] == src.name


# ---------------------------------------------------------------------------
# Cell -> File Explorer
# ---------------------------------------------------------------------------

def test_locate_resolves_a_sub_day_bin(w):
    """Regression: the heatmap's usual bins are 15 min or 2 h, and the entry
    lookup compares whole dates -- so a naive [start, end) spanned [d, d) and
    matched nothing."""
    src = _write_continuous()
    two_hours_in = int((_DAY + dt.timedelta(hours=2)).timestamp() * 1000)
    with TestClient(w.app) as client:
        r = client.get("/api/files/locate", params={
            "geosncl": _GEOSNCL,
            "start_ms": two_hours_in,
            "end_ms": two_hours_in + 2 * 3600 * 1000,
        })
    assert r.status_code == 200
    assert r.json()["path"] == str(src.relative_to(paths.base_dir()))


def test_locate_returns_the_source_not_the_completeness_file(w):
    src = _write_continuous()
    C.generate_completeness_file(src)
    with TestClient(w.app) as client:
        r = client.get("/api/files/locate", params={
            "geosncl": _GEOSNCL, "start_ms": int(_DAY.timestamp() * 1000), "end_ms": 0})
    assert r.json()["path"] == str(src.relative_to(paths.base_dir()))
    assert "completeness" not in r.json()["path"]


def test_locate_404s_when_nothing_was_downloaded(w):
    _write_continuous()
    with TestClient(w.app) as client:
        r = client.get("/api/files/locate", params={
            "geosncl": "NOPE.XX.LY_.00",
            "start_ms": int(_DAY.timestamp() * 1000), "end_ms": 0})
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Completeness-file summary and block colouring
# ---------------------------------------------------------------------------

def test_completeness_file_summary_reads_the_stored_restarts(w):
    """Reading them back out of the file is the whole point of storing them."""
    src = _write_with_gap(gap_minutes=30, n_each=60)
    out = C.generate_completeness_file(src)
    with TestClient(w.app) as client:
        body = _summary(client, out)
    labels = dict(body["rows"])
    assert labels[f"Restarts (gap > {C._GAP_SECONDS:g} s)"] == "1"
    assert "Mean completeness" in labels
    assert "Longest gap" in labels
    assert "blocks" not in body or not body["blocks"]   # no per-sample times


def test_a_legacy_completeness_file_says_so_rather_than_showing_zero(w):
    src = _write_continuous()
    out = C.completeness_path(src)
    C._write_stream(
        C.compute_completeness(pa.table({"time": pa.array([0, 1000], type=pa.int64())}))
        .drop_columns(list(C._REQUIRED_COLUMNS)),
        out,
    )
    with TestClient(w.app) as client:
        body = _summary(client, out)
    assert "not recorded" in dict(body["rows"])["Restarts"]


def test_block_spans_cover_every_point_exactly_once(w):
    """Spans overlap by one point on purpose (so no one-sample notch appears at
    a boundary), but must still start at 0 and reach the end."""
    times = [0.0, 1.0, 2.0, 10.0, 11.0, 20.0]
    spans = w._block_spans(times, [0.0, 10.0, 20.0])
    assert len(spans) == 3
    assert spans[0][0] == 0
    assert spans[-1][1] == len(times)
    for (lo, hi), (nlo, _) in zip(spans, spans[1:]):
        assert lo < hi
        assert nlo <= hi          # contiguous or overlapping, never a hole


def test_a_single_block_is_not_split(w):
    times = [0.0, 1.0, 2.0]
    assert w._block_spans(times, [0.0]) == [(0, 3)]


# ---------------------------------------------------------------------------
# Unknown API routes
# ---------------------------------------------------------------------------

def test_an_unknown_api_route_404s_rather_than_405s(w):
    """The SPA catch-all is GET-only and matches every path, so a POST to an
    endpoint this build does not have used to come back "405 Method Not
    Allowed" -- which reads as a caller bug rather than a stale server."""
    with TestClient(w.app) as client:
        r = client.post("/api/definitely-not-a-route", json={})
    assert r.status_code == 404
    assert "restart es-pos webserver" in r.json()["hint"]


def test_an_unknown_api_get_404s_instead_of_serving_the_spa(w):
    """The worst of the two stale-server failures: index.html with a 200, so a
    caller reading a field off the reply silently got undefined and carried on.
    That is exactly how a heatmap cell click ended up on an empty page."""
    with TestClient(w.app) as client:
        r = client.get("/api/files/locate-typo", params={"geosncl": "X", "start_ms": 1})
    assert r.status_code == 404
    assert r.headers["content-type"].startswith("application/json")


def test_spa_routes_still_serve_html(w):
    """The /api guard must not touch the SPA's own routes."""
    with TestClient(w.app) as client:
        r = client.get("/completeness")
    assert r.status_code in (200, 503)      # 503 only when the SPA is not built
    if r.status_code == 200:
        assert r.headers["content-type"].startswith("text/html")


def test_a_real_route_called_the_wrong_way_still_405s(w):
    """The 404 above must not swallow genuine method errors: matching /api this
    broadly stops Starlette looking, so the handler has to tell them apart."""
    with TestClient(w.app) as client:
        r = client.post("/api/config/data-directory", json={})
    assert r.status_code == 405
    assert "GET" in r.json()["allowed"]
    assert "GET" in r.headers.get("Allow", "")


def test_the_precache_route_accepts_post(w):
    """Pins the method, since the failure mode above is silent and confusing."""
    with TestClient(w.app) as client:
        r = client.post("/api/completeness/precache",
                        json={"lists": ["all"], "start": "2026-01-15", "end": "2026-01-16"})
    assert r.status_code == 200

"""
FastAPI server for GNSS position data visualization.

Serves:
  /api/stream-lists   list of station_list JSON file names
  /api/stations        station inventory (with optional list / search filter)
  /api/completeness    heatmap data: completeness + latency per 15-min (or coarser) bin
  /api/status          cache and server status
  /assets/*            compiled SPA static assets
  /*                   SPA index.html (client-side routing fallback)

Start via:
  es-pos webserver [--host HOST] [--port PORT] [--data-dir PATH]

File-index cache
----------------
At startup the server scans data/arrow/ and builds an in-memory index mapping
each geosncl to the list of (date, arrow_path, completeness_path) tuples.  A
background asyncio task refreshes the index every SCAN_INTERVAL_S seconds so
new files are picked up without a restart.

On-demand completeness generation
----------------------------------
When /api/completeness is called, any arrow file that lacks a .completeness.arrow
sibling is generated on-the-fly via earthscope_positions.completeness, then
cached in the index so subsequent requests return immediately.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import functools
import io
import json
import logging
import os
import pathlib
import re
import sys
import threading
import time
from collections import OrderedDict, defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

_log = logging.getLogger(__name__)

import numpy as np
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.ipc as ipc

from fastapi import FastAPI, Query, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from earthscope_positions import paths

_UTC = dt.timezone.utc

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

SCAN_INTERVAL_S = 60  # seconds between background index refreshes

_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="completeness-gen")
_ppsd_pool = ThreadPoolExecutor(
    max_workers=20,
    thread_name_prefix="ppsd-cache",
)

# Loaded at startup for the station builder map endpoint
_station_builder_coords = None  # earthscope_positions.coordinates.Coordinates | None

# Network names (RTDB:* / SHAKE:*) discovered at startup for the Station Builder
# "Load Network" dropdown.  Populated by a best-effort background query.
_networks_cache: list[str] = []
_networks_loaded: bool = False


# Externally-reachable base URL, used for callback URLs shown in the UI (e.g.
# the Replay curl commands).  Set from `es-pos webserver --hostname/--port`.
_public_hostname: str = "localhost"
_public_port: int = 8000


def set_public_base(hostname: str, port: int) -> None:
    global _public_hostname, _public_port
    _public_hostname = hostname or "localhost"
    _public_port = int(port)


def _public_base_url() -> str:
    return f"http://{_public_hostname}:{_public_port}"


def run_startup_preflight() -> None:
    """Blocking pre-flight run BEFORE the server starts accepting requests.

    1. Verify a valid JWT (the user has logged in at some point) — abort startup
       if not, since every discovery/fetch call needs it.
    2. Seed the editable coordinates.csv and export path-spec TOMLs from
       bundled resources (into <data-directory>/resources/) if absent.
    3. Preload the always-available default lists (all-streams / all-stations /
       shake-alert streams+stations) if any are missing.

    JWT failure is fatal (``SystemExit``); a preload/resource-seed failure is
    logged and tolerated so a transient API hiccup doesn't block the whole
    server.
    """
    # 1) JWT / login check — fatal if missing or unrefreshable.
    print("Pre-flight: checking EarthScope login …", file=sys.stderr)
    try:
        from earthscope_positions.fetch.positions_fetch import _ensure_token
        _ensure_token()   # raises SystemExit with a clear message if not logged in
        print("  auth     : OK", file=sys.stderr)
    except SystemExit:
        raise
    except Exception as exc:
        raise SystemExit(
            f"Pre-flight auth check failed: {exc}\n"
            "Log in with:  es user login   then restart the server."
        )

    # 2) Seed the editable resources — coordinates.csv and the export path-spec
    #    TOMLs — from the bundled copies if absent.
    try:
        from earthscope_positions import coordinates as _coords
        p = _coords.ensure_data_csv()
        print(f"  coords   : {p}", file=sys.stderr)
    except Exception as exc:
        print(f"  coords   : seed failed ({exc})", file=sys.stderr)

    try:
        for name in ("geojson_path_spec.toml", "miniseed_path_spec.toml"):
            paths.ensure_resource(name)
        print(f"  specs    : {paths.resources_dir()}", file=sys.stderr)
    except Exception as exc:
        print(f"  specs    : seed failed ({exc})", file=sys.stderr)

    # 3) Preload default lists (created only if missing).
    try:
        from earthscope_positions.stations import station_list as _sl
        created = _sl.preload_default_lists(log=lambda m: print(f"  {m}", file=sys.stderr))
        _sl.close_client()
        if created:
            print(f"  preload  : created {', '.join(created)}", file=sys.stderr)
        else:
            print("  preload  : default lists already present", file=sys.stderr)
    except Exception as exc:
        print(f"  preload  : failed ({exc}); continuing without default lists", file=sys.stderr)


def _project_root() -> pathlib.Path:
    # For locating the built SPA/README, independent of the data dir. CWD-based
    # (nearest ancestor with pyproject.toml) rather than __file__-based: a real
    # (non-editable) `pip install .` copies the code into site-packages, far
    # from the checkout's spa/spaBuild — this only works if run with the repo
    # checkout as CWD (e.g. the Docker image's WORKDIR), same as paths.py.
    return paths.project_root()


def _data_dir() -> pathlib.Path:
    return paths.arrow_dir()


def _stream_lists_dir() -> pathlib.Path:
    return paths.stream_lists_dir()


def _station_lists_dir() -> pathlib.Path:
    return paths.station_lists_dir()


def _child_env() -> dict[str, str]:
    """Environment for a child ``es-pos`` process.

    Propagates THIS server's resolved data directory so subprocesses land in
    the same tree rather than re-resolving and possibly picking a different
    one.  There is no ``--data-directory`` flag any more; the environment
    variable is the supported override, and passing it this way also carries
    the "already warned about a config mismatch" marker so children do not
    repeat that notice into the UI log on every run.
    """
    return {**os.environ, paths.ENV_VAR: str(paths.base_dir())}


def _spa_dir() -> pathlib.Path:
    return _project_root() / "spa" / "spaBuild"


# ---------------------------------------------------------------------------
# In-memory file index
# ---------------------------------------------------------------------------

@dataclass
class _FileEntry:
    arrow_path: pathlib.Path
    completeness_path: pathlib.Path | None  # None = not yet generated


# geosncl -> sorted list of (date, FileEntry)
_file_index: dict[str, list[tuple[dt.date, _FileEntry]]] = {}

# These asyncio.Locks are created during startup (requires a running event loop
# for Python < 3.10; creating them here is safe in 3.10+ but we init in startup
# to be explicit).
_index_lock: asyncio.Lock | None = None
_gen_locks_mu: asyncio.Lock | None = None
_gen_locks: dict[str, asyncio.Lock] = {}  # key: str(completeness_path)

_last_scan_time: float = 0.0
_last_scan_files: int = 0


def _completeness_path_for(arrow_path: pathlib.Path) -> pathlib.Path:
    return arrow_path.parent / (arrow_path.stem + ".completeness.arrow")


def _scan_data_dir_sync(data_dir: pathlib.Path) -> dict[str, list[tuple[dt.date, _FileEntry]]]:
    """Full directory scan — blocking, run in executor."""
    index: dict[str, list[tuple[dt.date, _FileEntry]]] = {}
    if not data_dir.exists():
        return index
    for arrow_path in sorted(data_dir.rglob("*.arrow")):
        if ".completeness" in arrow_path.name or "_ppsd" in arrow_path.name:
            continue
        # Expected layout: data_dir/GEOSNCL/YYYYMM/GEOSNCL_<dateT>_<dateT>.arrow
        try:
            geosncl = arrow_path.parent.parent.name
        except Exception:
            continue
        prefix = geosncl + "_"
        if not arrow_path.stem.startswith(prefix):
            continue
        rest = arrow_path.stem[len(prefix):]
        try:
            file_dt = dt.datetime.strptime(rest[:16], "%Y%m%dT%H%M%SZ")
        except ValueError:
            continue
        comp = _completeness_path_for(arrow_path)
        entry = _FileEntry(
            arrow_path=arrow_path,
            completeness_path=comp if comp.exists() else None,
        )
        index.setdefault(geosncl, []).append((file_dt.date(), entry))

    for entries in index.values():
        entries.sort(key=lambda x: x[0])
    return index


async def _refresh_index() -> None:
    """Rebuild _file_index from disk (scan runs in thread pool)."""
    global _last_scan_time, _last_scan_files
    loop = asyncio.get_event_loop()
    new_index = await loop.run_in_executor(None, _scan_data_dir_sync, _data_dir())
    async with _index_lock:  # type: ignore[union-attr]
        _file_index.clear()
        _file_index.update(new_index)
    _clear_table_cache()  # file set may have changed — don't serve stale content
    _last_scan_time = time.time()
    _last_scan_files = sum(len(v) for v in _file_index.values())


async def _background_scanner() -> None:
    while True:
        await asyncio.sleep(SCAN_INTERVAL_S)
        try:
            await _refresh_index()
        except Exception as exc:
            print(f"[file-index] scan error: {exc}", file=sys.stderr)


# ---------------------------------------------------------------------------
# On-demand completeness generation
# ---------------------------------------------------------------------------

async def _ensure_completeness(entry: _FileEntry) -> pathlib.Path | None:
    """
    If the completeness file for *entry* doesn't exist yet, generate it in a
    thread-pool worker (one concurrent generation per unique path).  Updates
    entry.completeness_path in place on success.
    """
    comp = _completeness_path_for(entry.arrow_path)
    if comp.exists():
        entry.completeness_path = comp
        return comp

    key = str(comp)
    async with _gen_locks_mu:  # type: ignore[union-attr]
        if key not in _gen_locks:
            _gen_locks[key] = asyncio.Lock()
    per_file_lock = _gen_locks[key]

    async with per_file_lock:
        # Double-check inside lock (another coroutine may have just generated it)
        if comp.exists():
            entry.completeness_path = comp
            return comp

        def _generate() -> pathlib.Path | None:
            from earthscope_positions.process.completeness import generate_completeness_file
            return generate_completeness_file(entry.arrow_path, overwrite=False, sampling_hz=1.0)

        loop = asyncio.get_event_loop()
        result: pathlib.Path | None = await loop.run_in_executor(_executor, _generate)
        if result is not None:
            entry.completeness_path = result
        return result


# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------

def _indexed_geosncls() -> list[str]:
    """All geosncls known to the file index (falls back to disk scan)."""
    if _file_index:
        return sorted(_file_index.keys())
    # Index not ready yet (called before startup completes)
    dd = _data_dir()
    if not dd.exists():
        return []
    return sorted(p.name for p in dd.iterdir() if p.is_dir() and not p.name.startswith("."))


def _list_stream_list_names() -> list[str]:
    d = _stream_lists_dir()
    if not d.exists():
        return []
    return sorted(p.stem for p in d.glob("*.jsonl"))


def _stream_validation():
    """The stream-list validation helpers (imported lazily to avoid a cycle)."""
    from earthscope_positions.stations import station_list as _sl
    return _sl


def _is_protected_list(name: str) -> bool:
    """all-streams is generated and is the membership reference for every other
    list, so it is not editable, renameable, or deletable from the UI."""
    return name.strip().lower() == _stream_validation().ALL_STREAMS_LIST


def _valid_stream_records(records: list[dict]) -> tuple[list[dict], list[str]]:
    """Split records into (usable, reasons-for-the-rest).

    Lists written before validation existed -- notably the NCEDC partner lists,
    which recorded bare {"geosncl": ...} for unmatched streams -- contain
    entries with no edid.  Those cannot be fetched, so they are dropped on read
    and counted, rather than being handed downstream to fail later.
    """
    sl = _stream_validation()
    good: list[dict] = []
    reasons: list[str] = []
    for rec in records:
        problem = sl.validate_stream_record(rec)
        if problem is None:
            good.append(rec)
        else:
            label = (rec.get("geosncl") or rec.get("edid") or "?") if isinstance(rec, dict) else "?"
            reasons.append(f"{label}: {problem}")
    return good, reasons


def _read_stream_list_file(path: pathlib.Path) -> list[dict]:
    """Read a stream list file in either JSONL or (legacy) JSON array format."""
    raw = path.read_bytes()
    if path.suffix == ".json":
        return json.loads(raw)
    return [json.loads(line) for line in raw.splitlines() if line.strip()]


def _geosncls_for_list(list_name: str) -> list[str]:
    """Return every geosncl that belongs to a named list (or 'all').

    Deliberately NOT filtered to what's already downloaded/indexed — most
    callers need to know a stream belongs to a list before it has any local
    data at all: Fetch Data's filter chips (that's the whole point — you're
    about to fetch what's missing), the Completeness page's "not tried"
    buckets, and station/stream trees for building lists or picking what to
    fetch next. Callers that specifically need "and has local data for this
    range" (replay, PPSD) already do their own file/date-range check
    afterward, so they're unaffected by a list containing not-yet-fetched
    streams.
    """
    if list_name == "all":
        return sorted(set(_all_list_geosncls()) | set(_indexed_geosncls()))
    d = _stream_lists_dir()
    path = d / f"{list_name}.jsonl"
    if not path.exists():
        path = d / f"{list_name}.json"   # backward compat
        if not path.exists():
            return []
    try:
        records = _read_stream_list_file(path)
    except Exception:
        return []
    result: list[str] = []
    for rec in records:
        g = rec.get("geosncl") or rec.get("edid", "")
        if g:
            result.append(g)
    return sorted(set(result))


def _entries_in_range(
    geosncl: str, start: dt.datetime, end: dt.datetime
) -> list[_FileEntry]:
    """Return FileEntry objects whose date falls in [start.date(), end.date())."""
    start_date = start.date()
    end_date = end.date()
    return [
        entry
        for (date, entry) in _file_index.get(geosncl, [])
        if start_date <= date < end_date
    ]


# ── Shared time-filtered-table cache ──────────────────────────────────────────
#
# /api/positions and /api/coherence both need the same thing per stream: every
# Arrow file in [start, end) read off disk, concatenated, and time-filtered.
# That's the expensive part (disk I/O + IPC decode + concat) — cache *that*,
# keyed on the exact (geosncl, start, end) triple, so repeat requests for it
# (switching the coherence component, reopening a dialog, a second chart using
# the same range) are served from memory.  Downstream per-request work
# (downsampling, column extraction) stays uncached since it's cheap and varies
# per call.
#
# Entries expire after _TABLE_CACHE_TTL_S, and the whole cache is cleared
# whenever the file index is refreshed (_refresh_index — every
# SCAN_INTERVAL_S, and on-demand right after a fetch job completes) since
# that's already the "something on disk may have changed" signal; the TTL is
# just a defensive upper bound on top of that.

_TABLE_CACHE_TTL_S = 300.0
_TABLE_CACHE_MAX_ENTRIES = 200
_table_cache: "OrderedDict[tuple[str, int, int], tuple[float, pa.Table]]" = OrderedDict()
_table_cache_lock = threading.Lock()


def _clear_table_cache() -> None:
    with _table_cache_lock:
        _table_cache.clear()


def _load_filtered_table(
    geosncl: str, start_dt: dt.datetime, end_dt: dt.datetime
) -> pa.Table | None:
    """Return the concatenated, time-filtered Arrow table for *geosncl* over
    [start_dt, end_dt), reusing a cached copy for the exact same request when
    one is still fresh.  None if there's no data at all in range."""
    start_ms = int(start_dt.timestamp() * 1000)
    end_ms = int(end_dt.timestamp() * 1000)
    key = (geosncl, start_ms, end_ms)

    now = time.monotonic()
    with _table_cache_lock:
        hit = _table_cache.get(key)
        if hit is not None:
            cached_at, table = hit
            if now - cached_at < _TABLE_CACHE_TTL_S:
                _table_cache.move_to_end(key)
                return table
            del _table_cache[key]

    entries = _entries_in_range(geosncl, start_dt, end_dt)
    if not entries:
        return None
    tables = []
    for entry in entries:
        try:
            buf = io.BytesIO(entry.arrow_path.read_bytes())
            tables.append(ipc.open_stream(buf).read_all())
        except Exception:
            continue
    if not tables:
        return None

    table = pa.concat_tables(tables)
    time_col = table.column("time")
    mask = pc.and_(
        pc.greater_equal(time_col, pa.scalar(start_ms, pa.int64())),
        pc.less(time_col, pa.scalar(end_ms, pa.int64())),
    )
    table = table.filter(mask).sort_by("time")

    with _table_cache_lock:
        _table_cache[key] = (now, table)
        _table_cache.move_to_end(key)
        while len(_table_cache) > _TABLE_CACHE_MAX_ENTRIES:
            _table_cache.popitem(last=False)

    return table


# ── Boolean station filter ──────────────────────────────────────────────────

def _glob_to_regex(pat: str) -> re.Pattern[str]:
    return re.compile(
        re.escape(pat.strip()).replace(r"\*", ".*").replace(r"\?", "."),
        re.IGNORECASE,
    )


def _match_term(term: str, geosncl: str) -> bool:
    term = term.strip()
    if not term:
        return True
    if "*" in term or "?" in term:
        return bool(_glob_to_regex(term).fullmatch(geosncl))
    return term.lower() in geosncl.lower()


def _tokenize_expr(expr: str) -> list[str]:
    tokens: list[str] = []
    i = 0
    while i < len(expr):
        c = expr[i]
        if c in "()|&":
            tokens.append(c)
            i += 1
        elif c.isspace():
            i += 1
        else:
            j = i
            while j < len(expr) and expr[j] not in "()|& \t\n":
                j += 1
            tokens.append(expr[i:j])
            i = j
    return [t for t in tokens if t]


class _ExprParser:
    """Recursive-descent parser: & binds tighter than |."""

    def __init__(self, tokens: list[str]) -> None:
        self._t = tokens
        self._pos = 0

    def _peek(self) -> str | None:
        return self._t[self._pos] if self._pos < len(self._t) else None

    def _consume(self) -> str:
        tok = self._t[self._pos]
        self._pos += 1
        return tok

    def parse(self):
        return self._or()

    def _or(self):
        left = self._and()
        while self._peek() == "|":
            self._consume()
            right = self._and()
            left = (lambda l, r: lambda g: l(g) or r(g))(left, right)
        return left

    def _and(self):
        left = self._atom()
        while self._peek() == "&":
            self._consume()
            right = self._atom()
            left = (lambda l, r: lambda g: l(g) and r(g))(left, right)
        return left

    def _atom(self):
        tok = self._peek()
        if tok == "(":
            self._consume()
            fn = self._or()
            if self._peek() == ")":
                self._consume()
            return fn
        if tok is not None and tok not in (")", "|", "&"):
            term = self._consume()
            return (lambda t: lambda g: _match_term(t, g))(term)
        return lambda g: True


def _filter_by_pattern(geosncls: list[str], expr: str) -> list[str]:
    """Filter by boolean expression: | or, & and, () grouping, * ? glob, substring."""
    if not expr.strip():
        return geosncls
    tokens = _tokenize_expr(expr)
    if not tokens:
        return geosncls
    try:
        match_fn = _ExprParser(tokens).parse()
        return [g for g in geosncls if match_fn(g)]
    except Exception:
        q = expr.lower()
        return [g for g in geosncls if q in g.lower()]


# ── Completeness aggregation ────────────────────────────────────────────────

def _load_no_data_records(geosncl: str, data_dir: pathlib.Path) -> dict[str, str]:
    """Return {date_iso: result} for all recorded fetch attempts.
    result is one of: 'no-data', 'error-400', 'error-422', …
    Reads no_data.jsonl first; falls back to legacy no_data.json."""
    records: dict[str, str] = {}
    jsonl = data_dir / geosncl / "no_data.jsonl"
    if jsonl.exists():
        for line in jsonl.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                date = rec.get("date", "")
                res  = rec.get("result", "no-data")
                if date:
                    records[date] = res  # later entries override earlier ones
            except Exception:
                pass
        return records
    # Legacy JSON fallback
    old = data_dir / geosncl / "no_data.json"
    if old.exists():
        try:
            for d in json.loads(old.read_bytes()).get("dates", []):
                records[d] = "no-data"
        except Exception:
            pass
    return records


def _read_completeness(path: pathlib.Path) -> pa.Table | None:
    try:
        buf = io.BytesIO(path.read_bytes())
        return ipc.open_stream(buf).read_all()
    except Exception:
        return None


def _aggregate_bins(table: pa.Table, target_bin_ms: int) -> dict[int, dict]:
    """Aggregate 15-min completeness rows into coarser bins (weighted-mean latency)."""
    result: dict[int, dict] = defaultdict(lambda: {
        "row_count": 0, "expected_count": 0,
        "lat_num": 0.0, "lat_den": 0,
        "dly_num": 0.0, "dly_den": 0,
    })
    for bs, rc, ec, il, pd_ in zip(
        table.column("bucket_start_ms").to_pylist(),
        table.column("row_count").to_pylist(),
        table.column("expected_count").to_pylist(),
        table.column("mean_ingest_latency_s").to_pylist(),
        table.column("mean_processing_delay_s").to_pylist(),
    ):
        coarser = (bs // target_bin_ms) * target_bin_ms
        g = result[coarser]
        g["row_count"] += rc
        g["expected_count"] += ec
        if il is not None and rc > 0:
            g["lat_num"] += il * rc
            g["lat_den"] += rc
        if pd_ is not None and rc > 0:
            g["dly_num"] += pd_ * rc
            g["dly_den"] += rc
    return dict(result)


def _auto_bin_minutes(start: dt.datetime, end: dt.datetime) -> int:
    """Finest bin size keeping columns ≤ 75 (~50-60 typical)."""
    span_m = (end - start).total_seconds() / 60
    for bin_m in (15, 30, 60, 120, 180, 360, 720, 1440, 2880, 10080):
        if span_m / bin_m <= 75:
            return bin_m
    return 10080


def _make_bucket_grid(start: dt.datetime, end: dt.datetime, bin_minutes: int) -> list[int]:
    bin_ms = bin_minutes * 60 * 1000
    start_ms = int(start.timestamp() * 1000)
    end_ms = int(end.timestamp() * 1000)
    first = (start_ms // bin_ms) * bin_ms
    return list(range(first, end_ms, bin_ms))


def _build_station_buckets(
    geosncl: str,
    entries: list[_FileEntry],
    bucket_grid: list[int],
    bin_ms: int,
    data_dir: pathlib.Path,
    no_data_records: dict[str, str],  # date_iso → result ("no-data" | "error-NNN")
) -> list[dict]:
    """Build heatmap bucket list from pre-fetched (and completeness-ensured) entries."""
    # Dates for which we have an arrow file — tried regardless of completeness status
    tried_dates: set[str] = set()
    for e in entries:
        stem = e.arrow_path.stem
        rest = stem[len(geosncl) + 1:]  # strip "GEOSNCL_"
        raw = rest[:8]  # "20260101"
        tried_dates.add(f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}")

    # Load and aggregate completeness files
    agg: dict[int, dict] = {}
    completeness_files = [e.completeness_path for e in entries if e.completeness_path]
    if completeness_files:
        tables = [t for cf in completeness_files if (t := _read_completeness(cf)) is not None]
        if tables:
            agg = _aggregate_bins(pa.concat_tables(tables), bin_ms)

    buckets = []
    for bs in bucket_grid:
        date_str = dt.datetime.fromtimestamp(bs / 1000, tz=_UTC).strftime("%Y-%m-%d")
        g = agg.get(bs)
        if g is not None:
            rc = g["row_count"]
            ec = g["expected_count"]
            comp = min(1.0, rc / ec) if ec > 0 else 0.0
            lat = g["lat_num"] / g["lat_den"] if g["lat_den"] > 0 else None
            dly = g["dly_num"] / g["dly_den"] if g["dly_den"] > 0 else None
            state = "has-data" if rc > 0 else "no-data"
        elif date_str in no_data_records:
            res = no_data_records[date_str]
            state = "error" if res.startswith("error-") else "no-data"
            rc, ec, comp, lat, dly = 0, 0, None, None, None
        elif date_str in tried_dates:
            rc, ec, comp, lat, dly, state = 0, 0, 0.0, None, None, "no-data"
        else:
            rc, ec, comp, lat, dly, state = 0, 0, None, None, None, "not-tried"

        buckets.append({
            "bucketStartMs": bs,
            "rowCount": rc,
            "expectedCount": ec,
            "completeness": comp,
            "meanIngestLatencyS": lat,
            "meanProcessingDelayS": dly,
            "state": state,
        })
    return buckets


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(title="GNSS Positions", docs_url="/api/docs")


class _NoCacheMiddleware(BaseHTTPMiddleware):
    """Add Cache-Control: no-store to every response except versioned SPA assets.

    Vite's hashed bundles under /assets/ are content-addressed and safe to
    cache indefinitely.  Everything else (index.html, API responses, favicon)
    must not be cached so browsers always pick up the latest build.
    """

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        if not request.url.path.startswith("/assets/"):
            response.headers["Cache-Control"] = "no-store"
        return response


app.add_middleware(_NoCacheMiddleware)


@app.on_event("startup")
async def _startup() -> None:
    global _index_lock, _gen_locks_mu, _station_builder_coords
    _index_lock = asyncio.Lock()
    _gen_locks_mu = asyncio.Lock()

    # Initial blocking scan (in executor so the event loop stays responsive)
    await _refresh_index()

    # Periodic background refresh
    asyncio.create_task(_background_scanner())

    # Load station coordinates for the builder map
    try:
        from earthscope_positions.coordinates import Coordinates
        _station_builder_coords = Coordinates()
        print(f"  coords   : {len(_station_builder_coords)} stations", file=sys.stderr)
    except Exception as exc:
        print(f"  coords   : not found ({exc})", file=sys.stderr)

    # Best-effort background discovery of RTDB:* / SHAKE:* networks for the
    # Station Builder "Load Network" dropdown (needs API auth / VPN).
    asyncio.create_task(_load_networks_bg())


async def _load_networks_bg() -> None:
    global _networks_cache, _networks_loaded
    loop = asyncio.get_event_loop()
    try:
        from earthscope_positions.stations.station_list import list_networks
        nets = await loop.run_in_executor(None, list_networks)
        _networks_cache = nets
        print(f"  networks : {len(nets)} (RTDB:*/SHAKE:*)", file=sys.stderr)
    except Exception as exc:
        print(f"  networks : lookup failed ({exc})", file=sys.stderr)
    finally:
        _networks_loaded = True


@app.on_event("shutdown")
async def _shutdown() -> None:
    # Signal any running replay to stop so the Kafka producer can flush and
    # release its internal C threads before the process exits.
    _replay_mod.cancel_replay()

    # Mount SPA assets
    spa = _spa_dir()
    if spa.exists():
        print(f"  spa      : {spa}", file=sys.stderr)
        if (spa / "assets").exists():
            app.mount("/assets", StaticFiles(directory=spa / "assets"), name="assets")
    else:
        print("  spa      : not built (run: cd spa/spaGenerator && npm run build)", file=sys.stderr)


# ── /api/config ──────────────────────────────────────────────────────────────

@app.get("/api/config")
async def api_config() -> dict:
    """Client-facing server config, incl. the externally-reachable base URL used
    for callback commands (e.g. Replay curl snippets)."""
    return {
        "base_url": _public_base_url(),
        "hostname": _public_hostname,
        "port": _public_port,
    }


# ── /api/status ──────────────────────────────────────────────────────────────

@app.get("/api/data-range")
async def api_data_range() -> dict:
    """Return the earliest and latest dates that have any position arrow files."""
    all_dates: list[dt.date] = [
        d for entries in _file_index.values() for d, _ in entries
    ]
    if not all_dates:
        return {"min": None, "max": None}
    return {
        "min": min(all_dates).isoformat(),
        "max": max(all_dates).isoformat(),
    }


@app.get("/api/status")
async def api_status() -> dict:
    total_files = sum(len(v) for v in _file_index.values())
    comp_files = sum(
        sum(1 for _, e in v if e.completeness_path is not None)
        for v in _file_index.values()
    )
    return {
        "stations": len(_file_index),
        "arrowFiles": total_files,
        "completenessFiles": comp_files,
        "lastScanAt": dt.datetime.fromtimestamp(_last_scan_time, tz=_UTC).isoformat()
        if _last_scan_time else None,
        "nextScanIn": max(0, round(SCAN_INTERVAL_S - (time.time() - _last_scan_time)))
        if _last_scan_time else None,
    }


# ── /api/stream-lists ───────────────────────────────────────────────────────

@app.get("/api/stream-lists/protected")
async def api_stream_lists_protected() -> dict:
    """Names the UI must not offer edit/rename/delete for."""
    return {"protected": [_stream_validation().ALL_STREAMS_LIST]}


@app.get("/api/stream-lists")
async def api_stream_lists() -> dict:
    return {"lists": _list_stream_list_names()}


@app.get("/api/stream-lists/filter-options")
async def api_stream_lists_filter_options(
    lists: list[str] = Query([]),
) -> JSONResponse:
    """Return available centers and combined sol_type codes for the given lists.

    If lists is empty, scans all station list files.
    """
    if lists:
        geosncl_set: set[str] = set()
        for lst in lists:
            geosncl_set.update(_geosncls_for_list(lst))
        geosncls = sorted(geosncl_set)
    else:
        geosncls = _all_list_geosncls()

    centers_set:   set[str] = set()
    sol_types_set: set[str] = set()
    for gs in geosncls:
        parts = gs.split(".")
        if len(parts) < 4:
            continue
        centers_set.add(parts[1])
        loc = parts[3]
        if len(loc) >= 2:
            sol_types_set.add(loc[:2])

    return JSONResponse({
        "centers":   sorted(centers_set),
        "sol_types": sorted(sol_types_set),
    })


_NCEDC_METADATA_URL = "https://ncedc.org/outgoing/gps/ShakeAlert/metadata/"

#: Authoritative ShakeAlert monument coordinates, published alongside the
#: per-network chanfiles.  Not to be confused with merged_chanfile_coord.dat.
_NCEDC_COORDS_FILE = "station_coords_extended.dat"


def _shakealert_coords_to_csv(text: str) -> tuple[str, int, int]:
    """Convert station_coords_extended.dat into coordinates CSV text.

    Whitespace-separated, ``#``-commented; columns 0-3 are
    ``station latitude longitude ellipsoidal_height`` and the rest (ECEF XYZ,
    epoch, network, status) is not used here.  Returns
    ``(csv_text, rows_parsed, rows_skipped)``.
    """
    out = ["station,latitude,longitude,height,source"]
    parsed = skipped = 0
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) < 4:
            skipped += 1
            continue
        station = parts[0].strip().upper()
        try:
            lat, lon, height = float(parts[1]), float(parts[2]), float(parts[3])
        except ValueError:
            skipped += 1
            continue
        if not station:
            skipped += 1
            continue
        out.append(f"{station},{lat},{lon},{height},shakealert")
        parsed += 1
    return "\n".join(out) + "\n", parsed, skipped

# NOTE: the old streaming /api/stream-lists/{shakealert-datasource,all-streams}
# endpoints were removed — those lists are now preloaded at server startup
# (run_startup_preflight → station_list.preload_default_lists).


@app.get("/api/station-builder/networks")
async def api_station_builder_networks(refresh: bool = False) -> JSONResponse:
    """Return the discovered RTDB:* / SHAKE:* network names for the dropdown.

    Populated in the background at startup; pass ?refresh=true to re-query.
    """
    global _networks_cache, _networks_loaded
    if refresh or not _networks_loaded:
        loop = asyncio.get_event_loop()
        try:
            from earthscope_positions.stations.station_list import list_networks
            _networks_cache = await loop.run_in_executor(None, list_networks)
            _networks_loaded = True
        except Exception as exc:
            return JSONResponse(
                {"networks": _networks_cache, "loaded": _networks_loaded, "error": str(exc)}
            )
    return JSONResponse({"networks": _networks_cache, "loaded": _networks_loaded})


@app.post("/api/station-builder/load-network", response_model=None)
async def api_station_builder_load_network(network: str = Query(...)) -> JSONResponse:
    """Fetch all gnss_ppp streams in *network* and save them as a station list.

    Returns the saved list name so the caller can make it the active list.
    """
    if not network.strip():
        return JSONResponse({"error": "network is required"}, status_code=400)
    loop = asyncio.get_event_loop()
    try:
        from earthscope_positions.stations.station_list import save_network_list
        name, records = await loop.run_in_executor(None, save_network_list, network)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=502)
    geosncls = [r["geosncl"] for r in records if r.get("geosncl")]
    return JSONResponse({
        "network": network,
        "name": name,
        "count": len(records),
        "geosncls": geosncls,
    })


#: NCEDC is served through a TLS-inspecting proxy on the EarthScope network,
#: so its chain terminates in a self-signed root Python does not trust and the
#: fetch fails with CERTIFICATE_VERIFY_FAILED.  Verification is disabled for
#: *these* fetches only -- a module-local context, never the process-wide
#: default -- so nothing else in the app loses certificate checking.  Set
#: ES_POS_VERIFY_NCEDC_TLS=1 to restore verification.
def _ncedc_ssl_context():
    import os
    import ssl

    if os.environ.get("ES_POS_VERIFY_NCEDC_TLS", "").strip() not in ("", "0", "false"):
        return None                      # None => urlopen uses the default checks
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def _fetch_url_sync(url: str) -> bytes:
    import urllib.request
    with urllib.request.urlopen(url, timeout=30, context=_ncedc_ssl_context()) as r:
        return r.read()


@app.get("/api/stream-lists/update-active-from-ncedc")
async def api_update_active_from_ncedc() -> StreamingResponse:
    """Download chanfile_XX.dat from NCEDC, cross-reference existing lists, write XX-Active.jsonl."""
    def _sse(obj: dict) -> str:
        return f"data: {json.dumps(obj)}\n\n"

    async def generate():
        loop = asyncio.get_event_loop()

        yield _sse({"type": "log", "msg": f"Fetching index: {_NCEDC_METADATA_URL}"})
        try:
            html_bytes = await loop.run_in_executor(None, _fetch_url_sync, _NCEDC_METADATA_URL)
        except Exception as exc:
            yield _sse({"type": "error", "msg": f"Failed to fetch index: {exc}"})
            yield _sse({"type": "done", "code": 1})
            return

        # The lookbehind matters: the index also lists merged_chanfile_coord.dat,
        # and an unanchored `chanfile_(\w+)\.dat` matches inside it, yielding a
        # bogus "coord" network and a 404 on chanfile_coord.dat.  Only filenames
        # that actually start with chanfile_ are partner networks.
        chanfile_codes = sorted(set(re.findall(
            r'(?<![A-Za-z0-9_-])chanfile_(\w+)\.dat',
            html_bytes.decode(errors="replace"),
        )))
        if not chanfile_codes:
            yield _sse({"type": "error", "msg": "No chanfile_XX.dat files found."})
            yield _sse({"type": "done", "code": 1})
            return

        yield _sse({"type": "log", "msg": f"Found {len(chanfile_codes)} chanfile(s): {', '.join(chanfile_codes)}"})

        # Build cross-reference from all existing station-list files
        yield _sse({"type": "log", "msg": "Cross-referencing existing station lists…"})
        all_records: dict[str, dict] = {}
        d = _stream_lists_dir()
        for path in sorted(d.iterdir()):
            if path.suffix not in (".jsonl", ".json"):
                continue
            try:
                for rec in _read_stream_list_file(path):
                    gs = rec.get("geosncl") or rec.get("edid", "")
                    if gs and gs not in all_records:
                        all_records[gs] = rec
            except Exception:
                pass
        yield _sse({"type": "log", "msg": f"  {len(all_records)} unique stream(s) in existing lists."})

        # Membership reference: a stream absent from all-streams cannot be
        # fetched, so it is skipped rather than written as a partial record.
        known_geosncls = _stream_validation().all_stream_geosncls()
        yield _sse({"type": "log",
                    "msg": f"  {len(known_geosncls)} stream(s) in all-streams "
                           f"(membership reference)."
                           if known_geosncls else
                           "  all-streams is empty — membership check skipped."})

        created: list[str] = []

        for code in chanfile_codes:
            center = code.upper()
            url = f"{_NCEDC_METADATA_URL}chanfile_{code}.dat"
            yield _sse({"type": "log", "msg": f"\nDownloading chanfile_{code}.dat…"})

            try:
                content = await loop.run_in_executor(None, _fetch_url_sync, url)
            except Exception as exc:
                yield _sse({"type": "error", "msg": f"  Failed: {exc}"})
                continue

            geosncls: set[str] = set()
            for line in content.decode(errors="replace").splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts_row = line.split()
                if len(parts_row) < 4:
                    continue
                network, station, location, channel = parts_row[0], parts_row[1], parts_row[2], parts_row[3]
                base_chan = channel[:2] + "_" if len(channel) >= 2 else channel
                geosncls.add(f"{station}.{network}.{base_chan}.{location}")

            yield _sse({"type": "log", "msg": f"  {len(geosncls)} unique stream(s) in chanfile."})

            # Only complete records go in.  Writing a bare {"geosncl": ...} for
            # an unmatched stream produced lists whose entries had no edid, could
            # not be fetched, and failed silently as "no data" later on.
            sl = _stream_validation()
            records: list[dict] = []
            unmatched: list[str] = []
            for gs in sorted(geosncls):
                rec = all_records.get(gs)
                in_all = (not known_geosncls) or gs in known_geosncls
                if rec is not None and in_all and sl.validate_stream_record(rec) is None:
                    records.append(rec)
                else:
                    unmatched.append(gs)
            yield _sse({"type": "log",
                        "msg": f"  {len(records)}/{len(geosncls)} matched in existing lists."})
            if unmatched:
                sample = ", ".join(unmatched[:5])
                more = f" (+{len(unmatched) - 5} more)" if len(unmatched) > 5 else ""
                yield _sse({"type": "log",
                            "msg": f"  Skipped {len(unmatched)} stream(s) with no complete "
                                   f"record in all-streams: {sample}{more}"})

            list_name = f"{center.lower()}-active"
            d.mkdir(parents=True, exist_ok=True)
            out_path = d / f"{list_name}.jsonl"
            out_path.write_text(
                "\n".join(json.dumps(rec, ensure_ascii=False) for rec in records) + "\n",
                encoding="utf-8",
            )
            created.append(list_name)
            yield _sse({"type": "log", "msg": f"  → Saved {list_name}.jsonl ({len(records)} stream(s))"})

        # ── Station coordinates ────────────────────────────────────────────
        # The same directory publishes the authoritative ShakeAlert monument
        # coordinates.  Merging them here keeps the map in step with the stream
        # lists that were just rebuilt from it.
        yield _sse({"type": "log", "msg": f"\nDownloading {_NCEDC_COORDS_FILE}…"})
        try:
            coord_bytes = await loop.run_in_executor(
                None, _fetch_url_sync, _NCEDC_METADATA_URL + _NCEDC_COORDS_FILE)
            csv_text, n_rows, n_bad = _shakealert_coords_to_csv(
                coord_bytes.decode(errors="replace"))
            if not n_rows:
                yield _sse({"type": "error", "msg": "  No coordinate rows parsed; skipped."})
            else:
                total, added, updated = await loop.run_in_executor(
                    None, _coords_mod.merge_upload, csv_text)
                _reload_coords()
                skipped = f", {n_bad} unparseable row(s)" if n_bad else ""
                yield _sse({"type": "log",
                            "msg": f"  {n_rows} coordinate(s) read{skipped}; "
                                   f"+{added} new, {updated} updated ({total} total)."})
        except Exception as exc:
            # Coordinates are a bonus here -- a failure must not undo the stream
            # lists that were already written.
            yield _sse({"type": "error", "msg": f"  Coordinate update failed: {exc}"})

        yield _sse({"type": "done", "code": 0,
                    "msg": f"Done. Created/updated: {', '.join(created)}. Reload the page to see new lists."})

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/stream-lists/{name}", response_model=None)
async def api_get_stream_list(name: str) -> JSONResponse:
    name = name.strip()
    if not name or ".." in name or "/" in name or "\\" in name:
        return JSONResponse({"error": "Invalid list name"}, status_code=400)
    d = _stream_lists_dir()
    path = d / f"{name}.jsonl"
    if not path.exists():
        path = d / f"{name}.json"        # backward compat
        if not path.exists():
            return JSONResponse({"error": "Not found"}, status_code=404)
    try:
        records = _read_stream_list_file(path)
        usable, reasons = _valid_stream_records(records)
        geosncls = sorted({str(r["geosncl"]) for r in usable if r.get("geosncl")})
        if reasons:
            _log.warning("[stream-lists] %r: dropped %d incomplete record(s)",
                         name, len(reasons))
        return JSONResponse({
            "name": name,
            "geosncls": geosncls,
            "total": len(records),
            "filtered": len(reasons),
            "filtered_reasons": reasons[:20],
            "protected": _is_protected_list(name),
        })
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.delete("/api/stream-lists/{name}", response_model=None)
async def api_delete_stream_list(name: str) -> JSONResponse:
    name = name.strip()
    if not name or ".." in name or "/" in name or "\\" in name:
        return JSONResponse({"error": "Invalid list name"}, status_code=400)
    if _is_protected_list(name):
        return JSONResponse(
            {"error": f"'{name}' is generated and is the reference every other stream list is validated against; it cannot be changed here. Rebuild it by deleting it and restarting the server."},
            status_code=403)
    d = _stream_lists_dir()
    for suffix in (".jsonl", ".json"):
        path = d / f"{name}{suffix}"
        if path.exists():
            path.unlink()
            _log.info("[stream-lists] deleted %r", name)
            return JSONResponse({"deleted": name})
    return JSONResponse({"error": "Not found"}, status_code=404)


def _bad_list_name(n: str) -> bool:
    return (not n) or ".." in n or "/" in n or "\\" in n


class _RenameListBody(BaseModel):
    new_name: str


@app.post("/api/stream-lists/{name}/rename", response_model=None)
async def api_rename_stream_list(name: str, body: _RenameListBody) -> JSONResponse:
    name = name.strip()
    new = body.new_name.strip()
    if _bad_list_name(name) or _bad_list_name(new):
        return JSONResponse({"error": "Invalid list name"}, status_code=400)
    if _is_protected_list(name) or _is_protected_list(new):
        return JSONResponse(
            {"error": f"'{_stream_validation().ALL_STREAMS_LIST}' is generated and is the "
                      f"reference every other stream list is validated against; it cannot "
                      f"be renamed or overwritten here."},
            status_code=403)
    d = _stream_lists_dir()
    src = None
    for suffix in (".jsonl", ".json"):
        p = d / f"{name}{suffix}"
        if p.exists():
            src = p
            break
    if src is None:
        return JSONResponse({"error": "Not found"}, status_code=404)
    if new == name:
        return JSONResponse({"old": name, "name": new})
    dst = d / f"{new}.jsonl"
    if dst.exists():
        return JSONResponse({"error": f"A list named {new!r} already exists"}, status_code=409)
    src.rename(dst)
    _log.info("[stream-lists] renamed %r -> %r", name, new)
    return JSONResponse({"old": name, "name": new})


@app.get("/api/stream-lists/{name}/raw", response_model=None)
async def api_get_stream_list_raw(name: str) -> JSONResponse:
    """Return the raw JSONL text of a station list (for the editor)."""
    name = name.strip()
    if _bad_list_name(name):
        return JSONResponse({"error": "Invalid list name"}, status_code=400)
    d = _stream_lists_dir()
    for suffix in (".jsonl", ".json"):
        p = d / f"{name}{suffix}"
        if p.exists():
            return JSONResponse({"name": name, "content": p.read_text(encoding="utf-8")})
    return JSONResponse({"error": "Not found"}, status_code=404)


class _RawListBody(BaseModel):
    content: str


@app.post("/api/stream-lists/{name}/raw", response_model=None)
async def api_save_stream_list_raw(name: str, body: _RawListBody) -> JSONResponse:
    """Save raw JSONL text to a stream list (the editor's Save / Save As).

    Every non-empty line must be a complete stream record --
    ``{"geosncl", "edid", "facility", "software"}`` -- and must appear in
    all-streams.  A partial record cannot be fetched, so it is rejected at the
    point of writing rather than discovered later as a silent no-data result.
    """
    name = name.strip()
    if _bad_list_name(name):
        return JSONResponse({"error": "Invalid list name"}, status_code=400)
    if _is_protected_list(name):
        return JSONResponse(
            {"error": f"'{name}' is generated and cannot be edited. It is the reference "
                      f"every other stream list is validated against."},
            status_code=403)

    sl = _stream_validation()
    errors = sl.validate_stream_list_text(body.content, sl.all_stream_geosncls() or None)
    if errors:
        shown = errors[:15]
        more = f"\n… and {len(errors) - len(shown)} more problem(s)" if len(errors) > len(shown) else ""
        return JSONResponse(
            {"error": "Stream list validation failed:\n" + "\n".join(shown) + more,
             "errors": errors},
            status_code=400)

    d = _stream_lists_dir()
    d.mkdir(parents=True, exist_ok=True)
    content = body.content if body.content.endswith("\n") else body.content + "\n"
    (d / f"{name}.jsonl").write_text(content, encoding="utf-8")
    _log.info("[stream-lists] saved raw %r (%d bytes)", name, len(content))
    return JSONResponse({"name": name})


class _SaveListBody(BaseModel):
    geosncls: list[str]


@app.post("/api/stream-lists/{name}", response_model=None)
async def api_save_stream_list(name: str, body: _SaveListBody) -> dict:
    name = name.strip()
    if not name or ".." in name or "/" in name or "\\" in name:
        return JSONResponse({"error": "Invalid list name"}, status_code=400)
    d = _stream_lists_dir()
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{name}.jsonl"
    # Include edid when known (via the same geosncl -> edid map "Fetch
    # Missing" uses) so the saved file works directly with `es-pos fetch
    # --list` too, not just the web UI's own fetch button — without it, the
    # API is queried with the geosncl string as stream_id (a ULID param) and
    # 422s on every request, which reads as "no-data" everywhere it's not
    # explicitly checked for.
    # Write COMPLETE records.  Emitting {"geosncl": g} (or geosncl+edid only)
    # for anything unresolved is what produced lists that later failed
    # validation and could not be fetched -- facility/software come from the
    # all-streams superset, which is the reference every list is checked
    # against, with the edid map as a fallback for streams it predates.
    sl = _stream_validation()
    reference = {
        str(r["geosncl"]): r for r in sl.read_stream_list_records(sl.ALL_STREAMS_LIST)
        if r.get("geosncl")
    }
    edid_map = _geosncl_edid_map()

    records: list[dict] = []
    skipped: list[str] = []
    for g in sorted(set(body.geosncls)):
        rec = reference.get(g)
        if rec is None and g in edid_map:
            rec = {"geosncl": g, "edid": edid_map[g]}
        if rec is None or sl.validate_stream_record(rec) is not None:
            skipped.append(g)
            continue
        records.append({f: rec[f] for f in sl.STREAM_RECORD_FIELDS})

    if skipped:
        _log.warning("[stream-lists] %r: skipped %d incomplete stream(s): %s",
                     name, len(skipped), ", ".join(skipped[:5]))

    path.write_text("\n".join(json.dumps(r) for r in records) + "\n")
    _log.info("[stream-lists] saved %r (%d streams, %d skipped)",
              name, len(records), len(skipped))
    return {"name": name, "count": len(records),
            "skipped": len(skipped), "skipped_geosncls": skipped[:20]}


# ── /api/station-lists (station-code lists — Station List Builder) ────────────────
#
# Station lists hold station codes ({"station": "P143"} per line) under
# <base>/station-lists/.  They are the down-selected-stations lists produced by the
# Station List Builder and used as include/exclude sets by the Stream List
# Builder.  Endpoints mirror /api/stream-lists but for the station directory.

def _list_station_list_names() -> list[str]:
    d = _station_lists_dir()
    if not d.exists():
        return []
    return sorted(p.stem for p in d.glob("*.jsonl"))


def _stations_for_list(list_name: str) -> list[str]:
    """Return the station codes in a named station list (upper-cased, sorted, unique)."""
    d = _station_lists_dir()
    path = d / f"{list_name}.jsonl"
    if not path.exists():
        return []
    out: set[str] = set()
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            station = (rec.get("station") or "").strip().upper()
            if station:
                out.add(station)
    except Exception:
        return []
    return sorted(out)


@app.get("/api/station-lists")
async def api_station_lists() -> dict:
    return {"lists": _list_station_list_names()}


@app.get("/api/station-lists/{name}", response_model=None)
async def api_get_station_list(name: str) -> JSONResponse:
    name = name.strip()
    if _bad_list_name(name):
        return JSONResponse({"error": "Invalid list name"}, status_code=400)
    if not (_station_lists_dir() / f"{name}.jsonl").exists():
        return JSONResponse({"error": "Not found"}, status_code=404)
    return JSONResponse({"name": name, "stations": _stations_for_list(name)})


@app.delete("/api/station-lists/{name}", response_model=None)
async def api_delete_station_list(name: str) -> JSONResponse:
    name = name.strip()
    if _bad_list_name(name):
        return JSONResponse({"error": "Invalid list name"}, status_code=400)
    path = _station_lists_dir() / f"{name}.jsonl"
    if path.exists():
        path.unlink()
        _log.info("[station-lists] deleted %r", name)
        return JSONResponse({"deleted": name})
    return JSONResponse({"error": "Not found"}, status_code=404)


@app.post("/api/station-lists/{name}/rename", response_model=None)
async def api_rename_station_list(name: str, body: _RenameListBody) -> JSONResponse:
    name = name.strip()
    new = body.new_name.strip()
    if _bad_list_name(name) or _bad_list_name(new):
        return JSONResponse({"error": "Invalid list name"}, status_code=400)
    d = _station_lists_dir()
    src = d / f"{name}.jsonl"
    if not src.exists():
        return JSONResponse({"error": "Not found"}, status_code=404)
    if new == name:
        return JSONResponse({"old": name, "name": new})
    dst = d / f"{new}.jsonl"
    if dst.exists():
        return JSONResponse({"error": f"A list named {new!r} already exists"}, status_code=409)
    src.rename(dst)
    _log.info("[station-lists] renamed %r -> %r", name, new)
    return JSONResponse({"old": name, "name": new})


@app.get("/api/station-lists/{name}/raw", response_model=None)
async def api_get_station_list_raw(name: str) -> JSONResponse:
    name = name.strip()
    if _bad_list_name(name):
        return JSONResponse({"error": "Invalid list name"}, status_code=400)
    p = _station_lists_dir() / f"{name}.jsonl"
    if not p.exists():
        return JSONResponse({"error": "Not found"}, status_code=404)
    return JSONResponse({"name": name, "content": p.read_text(encoding="utf-8")})


@app.post("/api/station-lists/{name}/raw", response_model=None)
async def api_save_station_list_raw(name: str, body: _RawListBody) -> JSONResponse:
    """Save raw JSONL text to a station list (editor). Each non-empty line must be a
    JSON object with a non-empty 'station'."""
    name = name.strip()
    if _bad_list_name(name):
        return JSONResponse({"error": "Invalid list name"}, status_code=400)
    for i, line in enumerate(body.content.splitlines(), start=1):
        s = line.strip()
        if not s:
            continue
        try:
            rec = json.loads(s)
        except Exception as exc:
            return JSONResponse({"error": f"Invalid JSON on line {i}: {exc}"}, status_code=400)
        if not isinstance(rec, dict) or not str(rec.get("station", "")).strip():
            return JSONResponse(
                {"error": f"Line {i}: each row needs a non-empty \"station\""}, status_code=400)
    d = _station_lists_dir()
    d.mkdir(parents=True, exist_ok=True)
    content = body.content if body.content.endswith("\n") else body.content + "\n"
    (d / f"{name}.jsonl").write_text(content, encoding="utf-8")
    _log.info("[station-lists] saved raw %r (%d bytes)", name, len(content))
    return JSONResponse({"name": name})


class _SaveStationListBody(BaseModel):
    stations: list[str]


@app.post("/api/station-lists/{name}", response_model=None)
async def api_save_station_list(name: str, body: _SaveStationListBody) -> dict:
    name = name.strip()
    if _bad_list_name(name):
        return JSONResponse({"error": "Invalid list name"}, status_code=400)
    d = _station_lists_dir()
    d.mkdir(parents=True, exist_ok=True)
    stations = sorted({s.strip().upper() for s in body.stations if s and s.strip()})
    lines = "\n".join(json.dumps({"station": s}) for s in stations) + "\n"
    (d / f"{name}.jsonl").write_text(lines)
    _log.info("[station-lists] saved %r (%d stations)", name, len(stations))
    return {"name": name, "count": len(stations)}


@app.get("/api/station-builder/network-stations")
async def api_station_builder_network_stations(
    network: str = Query(...),
    refresh: bool = Query(False),
) -> JSONResponse:
    """Station codes in a network, saving them as a station list on first use.

    Loading a network leaves behind a reusable station list named after it
    rather than only an in-memory selection.  Once that list exists it is read
    from disk instead of re-querying the API — a full network query is slow,
    and re-fetching would silently discard any hand-edits to the list.  Pass
    ``refresh=true`` to re-query and overwrite on purpose.
    """
    if not network.strip():
        return JSONResponse({"error": "network is required"}, status_code=400)
    loop = asyncio.get_event_loop()
    try:
        from earthscope_positions.stations.station_list import network_station_list
        name, stations, cached = await loop.run_in_executor(
            None, functools.partial(network_station_list, network, refresh=refresh),
        )
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=502)
    return JSONResponse({
        "network": network,
        "name": name,
        "stations": stations,
        "count": len(stations),
        "cached": cached,
    })


# ── /api/stations ────────────────────────────────────────────────────────────

@app.get("/api/stations")
async def api_stations(
    list: str = Query("all"),
    search: str = Query(""),
) -> dict:
    geosncls = _geosncls_for_list(list)
    if search:
        geosncls = _filter_by_pattern(geosncls, search)
    return {"stations": [{"geosncl": g} for g in geosncls], "total": len(geosncls)}


# ── /api/completeness ────────────────────────────────────────────────────────

@app.get("/api/completeness")
async def api_completeness(
    list: str = Query("all"),
    search: str = Query(""),
    start: str = Query(...),
    end: str = Query(...),
    page: int = Query(0, ge=0),
    size: int = Query(50, ge=1, le=500),
) -> dict:
    try:
        start_dt = dt.datetime.fromisoformat(start).replace(tzinfo=_UTC)
        end_dt = dt.datetime.fromisoformat(end).replace(tzinfo=_UTC)
    except ValueError:
        return JSONResponse({"error": "Invalid date format. Use YYYY-MM-DD."}, status_code=400)
    if end_dt <= start_dt:
        return JSONResponse({"error": "end must be after start"}, status_code=400)

    dd = _data_dir()
    geosncls = _geosncls_for_list(list)
    if search:
        geosncls = _filter_by_pattern(geosncls, search)

    total = len(geosncls)
    page_geosncls = geosncls[page * size: (page + 1) * size]

    bin_minutes = _auto_bin_minutes(start_dt, end_dt)
    bin_ms = bin_minutes * 60 * 1000
    bucket_grid = _make_bucket_grid(start_dt, end_dt, bin_minutes)

    # Ensure completeness files exist for all entries in this page (on-demand generation)
    gen_tasks = []
    page_entries: dict[str, list[_FileEntry]] = {}
    for geosncl in page_geosncls:
        entries = _entries_in_range(geosncl, start_dt, end_dt)
        page_entries[geosncl] = entries
        for entry in entries:
            if entry.completeness_path is None:
                gen_tasks.append(_ensure_completeness(entry))

    if gen_tasks:
        await asyncio.gather(*gen_tasks)

    # Build heatmap buckets
    stations = []
    for geosncl in page_geosncls:
        no_data = _load_no_data_records(geosncl, dd)
        buckets = _build_station_buckets(
            geosncl, page_entries[geosncl], bucket_grid, bin_ms, dd, no_data
        )
        stations.append({"geosncl": geosncl, "buckets": buckets})

    return {
        "bucketMs": bin_ms,
        "binMinutes": bin_minutes,
        "bucketStarts": bucket_grid,
        "stations": stations,
        "total": total,
        "page": page,
        "pageSize": size,
        "totalPages": max(1, -(-total // size)),
    }


# ── /api/positions ───────────────────────────────────────────────────────────

@app.get("/api/positions")
async def api_positions(
    geosncls: str = Query(..., description="Comma-separated geosncl codes"),
    start: str = Query(...),
    end: str = Query(...),
    max_points: int = Query(2000, ge=100, le=20000),
    downsample: bool = Query(True),
) -> dict:
    try:
        start_dt = dt.datetime.fromisoformat(start).replace(tzinfo=_UTC)
        end_dt = dt.datetime.fromisoformat(end).replace(tzinfo=_UTC)
    except ValueError:
        return JSONResponse({"error": "Invalid date format. Use YYYY-MM-DD."}, status_code=400)

    start_ms = int(start_dt.timestamp() * 1000)
    end_ms = int(end_dt.timestamp() * 1000)
    geosncl_list = [g.strip() for g in geosncls.split(",") if g.strip()]

    def _load_one(geosncl: str) -> dict:
        table = _load_filtered_table(geosncl, start_dt, end_dt)
        if table is None:
            return {"geosncl": geosncl, "times": [], "east": [], "north": [], "up": [],
                    "sigE": [], "sigN": [], "sigU": [], "downsampleFactor": 1}

        n = len(table)
        factor = 1
        if downsample and n > max_points:
            factor = max(1, n // max_points)
            indices = list(range(0, n, factor))[:max_points]
            table = table.take(indices)

        def _col(name: str) -> list:
            try:
                return table.column(name).to_pylist()
            except Exception:
                return [None] * len(table)

        return {
            "geosncl": geosncl,
            "times": _col("time"),
            "east":  _col("east"),
            "north": _col("north"),
            "up":    _col("up"),
            "sigE":  _col("sigEE"),
            "sigN":  _col("sigNN"),
            "sigU":  _col("sigUU"),
            "downsampleFactor": factor,
        }

    loop = asyncio.get_event_loop()
    results = await asyncio.gather(*[
        loop.run_in_executor(_executor, _load_one, g)
        for g in geosncl_list
    ])
    payload = {"stations": list(results)}
    total_pts = sum(len(s["times"]) for s in payload["stations"])
    _log.info("[positions] %d station(s), %d total points", len(geosncl_list), total_pts)
    return payload


# ── /api/coherence, /api/kle, /api/positions/common-mode-removed ────────────
#
# All three analyze the same thing (a set of streams' position data over a
# date range) in different ways, so they share validation + full-resolution
# loading (_validate_and_load_dense) — see analysis/coherence.py and
# analysis/kle.py for the actual math.

_ANALYSIS_MIN_STREAMS = 2
_COHERENCE_MAX_STREAMS = 35  # pairwise -> O(n^2) pairs; KLE/PCA have no cap


def _reject_outliers(
    times: np.ndarray, values: np.ndarray, threshold_m: float | None,
) -> tuple[np.ndarray, np.ndarray]:
    """Drop samples more than *threshold_m* metres from this stream's own
    median.  Variance-based analysis (KLE/PCA/coherence all pick out the
    *maximum-variance* direction) is extremely sensitive to a single gross
    outlier — e.g. a multi-km bad fix — even though it's a single point: it
    can inflate that one stream's variance by many orders of magnitude and
    make the whole decomposition collapse onto it ("mode 1 is 100% one
    station, everything else 0").  Median (not mean/stddev) is what makes
    this robust to exactly that case — a single outlier barely moves it."""
    if threshold_m is None or len(values) == 0:
        return times, values
    median = float(np.median(values))
    keep = np.abs(values - median) <= threshold_m
    return times[keep], values[keep]


def _load_component_raw(
    geosncl: str, comp: str, start_dt: dt.datetime, end_dt: dt.datetime,
    *, outlier_m: float | None = None,
):
    """Load one stream's (time_ms, value) arrays for *comp*, full resolution
    (no downsampling — this analysis needs the real, evenly-spaced sample
    sequence, not a plot-oriented thinned one)."""
    table = _load_filtered_table(geosncl, start_dt, end_dt)
    if table is None:
        return np.array([], dtype=np.int64), np.array([], dtype=np.float64)
    times = table.column("time").to_numpy(zero_copy_only=False)
    values = table.column(comp).to_numpy(zero_copy_only=False)
    valid = ~np.isnan(values)
    times, values = times[valid], values[valid]
    return _reject_outliers(times, values, outlier_m)


def _parse_analysis_request(
    geosncls: str, start: str, end: str, *, max_streams: int | None = None,
) -> tuple[list[str], dt.datetime, dt.datetime, JSONResponse | None]:
    """Shared validation for the coherence/KLE/PCA/common-mode-removed
    endpoints.  Returns (geosncl_list, start_dt, end_dt, None) on success, or
    (..., ..., ..., error_response) — check the last element first.

    *max_streams* is opt-in (only coherence passes one — it's pairwise, so
    O(n^2) pairs; KLE/PCA scale linearly and have no cap)."""
    try:
        start_dt = dt.datetime.fromisoformat(start).replace(tzinfo=_UTC)
        end_dt = dt.datetime.fromisoformat(end).replace(tzinfo=_UTC)
    except ValueError:
        return [], dt.datetime.min, dt.datetime.min, JSONResponse(
            {"error": "Invalid date format. Use YYYY-MM-DD."}, status_code=400
        )
    if end_dt <= start_dt:
        return [], start_dt, end_dt, JSONResponse({"error": "end must be after start"}, status_code=400)

    geosncl_list = sorted({g.strip() for g in geosncls.split(",") if g.strip()})
    if len(geosncl_list) < _ANALYSIS_MIN_STREAMS:
        return [], start_dt, end_dt, JSONResponse(
            {"error": f"Select at least {_ANALYSIS_MIN_STREAMS} streams."}, status_code=400
        )
    if max_streams is not None and len(geosncl_list) > max_streams:
        return [], start_dt, end_dt, JSONResponse(
            {"error": f"Select at most {max_streams} streams (got {len(geosncl_list)})."},
            status_code=400,
        )
    return geosncl_list, start_dt, end_dt, None


async def _load_dense_component(
    geosncl_list: list[str], component: str, start_dt: dt.datetime, end_dt: dt.datetime,
    *, outlier_m: float | None = None,
) -> dict[str, np.ndarray]:
    """Load + densify one component for every stream, in parallel."""
    from earthscope_positions.analysis import coherence as coh

    start_ms = int(start_dt.timestamp() * 1000)
    end_ms = int(end_dt.timestamp() * 1000)
    loop = asyncio.get_event_loop()

    def _load_and_densify(geosncl: str) -> np.ndarray:
        times, values = _load_component_raw(geosncl, component, start_dt, end_dt, outlier_m=outlier_m)
        return coh.densify_1hz(times, values, start_ms, end_ms)

    dense_arrays = await asyncio.gather(*[
        loop.run_in_executor(_executor, _load_and_densify, g) for g in geosncl_list
    ])
    return dict(zip(geosncl_list, dense_arrays))


@app.get("/api/coherence")
async def api_coherence(
    geosncls: str = Query(..., description=f"Comma-separated geosncl codes (2-{_COHERENCE_MAX_STREAMS})"),
    start: str = Query(...),
    end: str = Query(...),
    component: str = Query("east", pattern="^(east|north|up)$"),
    outlier_m: float | None = Query(
        None, gt=0,
        description="Reject samples more than this many metres from each stream's own median before analysis",
    ),
) -> JSONResponse:
    """Pairwise magnitude-squared coherence spectrum between every pair of
    streams, all on one shared frequency axis — see analysis.coherence.

    Always loads full-resolution data directly for whatever *geosncls* the
    caller passes, independent of any positions-page cache or how those
    streams were selected (one at a time vs. in bulk) — the two access
    patterns must not affect what's analyzed.  Capped at
    _COHERENCE_MAX_STREAMS since this is pairwise (O(n^2) pairs) — unlike
    KLE/PCA, which scale linearly and have no such cap.
    """
    from earthscope_positions.analysis import coherence as coh

    geosncl_list, start_dt, end_dt, err = _parse_analysis_request(
        geosncls, start, end, max_streams=_COHERENCE_MAX_STREAMS,
    )
    if err is not None:
        return err

    dense = await _load_dense_component(geosncl_list, component, start_dt, end_dt, outlier_m=outlier_m)
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(_executor, coh.pairwise_coherence_spectra, dense)
    result["component"] = component
    result["start"] = start
    result["end"] = end
    _log.info(
        "[coherence] %d stream(s), %s, %s -> %s, %d pair(s) skipped",
        len(geosncl_list), component, start, end, len(result["pairs_skipped"]),
    )
    return JSONResponse(result)


@app.get("/api/kle")
async def api_kle(
    geosncls: str = Query(..., description="Comma-separated geosncl codes (2 or more)"),
    start: str = Query(...),
    end: str = Query(...),
    component: str = Query("east", pattern="^(east|north|up)$"),
    n_modes: int = Query(5, ge=1, le=20),
    max_points: int = Query(2000, ge=100, le=20000),
    outlier_m: float | None = Query(
        None, gt=0,
        description="Reject samples more than this many metres from each stream's own median before analysis",
    ),
) -> JSONResponse:
    """Karhunen-Loeve (network PCA) decomposition — see analysis.kle.

    Alongside each mode's spatial loadings, also returns its reconstructed
    time series (via kle.reconstruct_mode) — downsampled the same way
    /api/positions is, since it's on the same dense 1 Hz grid — so the SPA
    can show what a mode actually looks like in time, not just which streams
    it's concentrated in.
    """
    from earthscope_positions.analysis import kle

    geosncl_list, start_dt, end_dt, err = _parse_analysis_request(geosncls, start, end)
    if err is not None:
        return err

    dense = await _load_dense_component(geosncl_list, component, start_dt, end_dt, outlier_m=outlier_m)
    loop = asyncio.get_event_loop()

    def _compute() -> tuple[dict, list[list[float | None]], np.ndarray, int]:
        result = kle.karhunen_loeve(dense, n_modes=min(n_modes, len(geosncl_list)))
        geosncls_sorted = result["geosncls"]
        n_t = len(dense[geosncls_sorted[0]]) if geosncls_sorted else 0
        indices = np.arange(n_t)
        factor = 1
        if n_t > max_points:
            factor = max(1, n_t // max_points)
            indices = indices[::factor][:max_points]
        mode_series: list[list[float | None]] = []
        for k in range(result["n_modes"]):
            pc = kle.reconstruct_mode(dense, geosncls_sorted, result["loadings"][k])
            sub = pc[indices]
            mode_series.append([None if np.isnan(v) else float(v) for v in sub])
        return result, mode_series, indices, factor

    result, mode_series, indices, factor = await loop.run_in_executor(_executor, _compute)

    start_ms = int(start_dt.timestamp() * 1000)
    result["modeTimes"] = (start_ms + 1000 * indices).tolist()
    result["modeSeries"] = mode_series
    result["modeDownsampleFactor"] = factor
    result["component"] = component
    result["start"] = start
    result["end"] = end
    _log.info(
        "[kle] %d stream(s), %s, %s -> %s: mode 1 explains %.1f%%",
        len(geosncl_list), component, start, end,
        result["variance_explained_pct"][0] if result["variance_explained_pct"] else 0.0,
    )
    return JSONResponse(result)


@app.get("/api/pca")
async def api_pca(
    geosncls: str = Query(..., description="Comma-separated geosncl codes (2 or more)"),
    start: str = Query(...),
    end: str = Query(...),
    component: str = Query("east", pattern="^(east|north|up)$"),
    n_modes: int = Query(5, ge=1, le=20),
    max_points: int = Query(2000, ge=100, le=20000),
    outlier_m: float | None = Query(
        None, gt=0,
        description="Reject samples more than this many metres from each stream's own median before analysis",
    ),
) -> JSONResponse:
    """Classical PCA (network decomposition) — see analysis.pca.

    Sibling of /api/kle: same response shape (variance_explained_pct,
    loadings, modeTimes/modeSeries), but built only from epochs where every
    selected stream has simultaneous data (n_complete_epochs), rather than
    KLE's pairwise-complete covariance — see analysis/pca.py for why that
    tradeoff exists.
    """
    from earthscope_positions.analysis import pca as pca_mod

    geosncl_list, start_dt, end_dt, err = _parse_analysis_request(geosncls, start, end)
    if err is not None:
        return err

    dense = await _load_dense_component(geosncl_list, component, start_dt, end_dt, outlier_m=outlier_m)
    loop = asyncio.get_event_loop()
    start_ms = int(start_dt.timestamp() * 1000)

    def _compute() -> tuple[dict, list[list[float | None]], list[int], int]:
        result = pca_mod.principal_component_analysis(dense, n_modes=min(n_modes, len(geosncl_list)))
        if not result["mode_series"]:
            result.pop("mode_series")
            return result, [], [], 1

        # Unlike KLE (whose reconstructed mode is defined almost everywhere via
        # weighted least squares), PCA's mode is only defined at the epochs
        # where every stream overlapped — often a small, scattered fraction of
        # the requested range with 10s of streams.  Downsampling by striding
        # the *full* grid (as /api/kle does) can easily land every sampled
        # point outside that fraction, making the chart look empty even
        # though n_complete_epochs > 0.  So sample from the valid subset
        # itself, and mark real gaps (not just "not sampled this time")
        # with an explicit None so the chart doesn't draw a straight line
        # across a stretch the network never fully covered.
        valid_idx = np.where(~np.isnan(result["mode_series"][0]))[0]
        factor = 1
        if len(valid_idx) > max_points:
            factor = max(1, len(valid_idx) // max_points)
            valid_idx = valid_idx[::factor][:max_points]

        gap_thresh = max(3 * factor, 3)
        times_ms: list[int] = []
        mode_series: list[list[float | None]] = [[] for _ in result["mode_series"]]
        prev_idx: int | None = None
        for idx in valid_idx.tolist():
            if prev_idx is not None and idx - prev_idx > gap_thresh:
                times_ms.append(start_ms + 1000 * ((prev_idx + idx) // 2))
                for series in mode_series:
                    series.append(None)
            times_ms.append(start_ms + 1000 * idx)
            for k, arr in enumerate(result["mode_series"]):
                v = arr[idx]
                mode_series[k].append(None if np.isnan(v) else float(v))
            prev_idx = idx

        result.pop("mode_series")
        return result, mode_series, times_ms, factor

    result, mode_series, times_ms, factor = await loop.run_in_executor(_executor, _compute)

    result["modeTimes"] = times_ms
    result["modeSeries"] = mode_series
    result["modeDownsampleFactor"] = factor
    result["component"] = component
    result["start"] = start
    result["end"] = end
    _log.info(
        "[pca] %d stream(s), %s, %s -> %s: %d complete epoch(s), mode 1 explains %.1f%%",
        len(geosncl_list), component, start, end, result["n_complete_epochs"],
        result["variance_explained_pct"][0] if result["variance_explained_pct"] else 0.0,
    )
    return JSONResponse(result)


@app.get("/api/positions/common-mode-removed")
async def api_positions_common_mode_removed(
    geosncls: str = Query(..., description="Comma-separated geosncl codes (2 or more)"),
    start: str = Query(...),
    end: str = Query(...),
    method: str = Query("kle", pattern="^(kle|pca)$"),
    n_modes_removed: int = Query(1, ge=1, le=5),
    max_points: int = Query(2000, ge=100, le=20000),
    downsample: bool = Query(True),
    outlier_m: float | None = Query(
        None, gt=0,
        description="Reject samples more than this many metres from each stream's own median before analysis",
    ),
) -> JSONResponse:
    """Each selected stream's East/North/Up series with the leading common
    mode(s) removed (independently per component), via either KLE
    (kle.common_mode_removed) or classical PCA (pca.pca_common_mode_removed —
    see analysis/pca.py for why PCA leaves epochs unmodified wherever the
    whole network doesn't overlap).  Same response shape as /api/positions
    so the frontend can plot it the same way."""
    from earthscope_positions.analysis import kle
    from earthscope_positions.analysis import pca as pca_mod

    geosncl_list, start_dt, end_dt, err = _parse_analysis_request(geosncls, start, end)
    if err is not None:
        return err

    start_ms = int(start_dt.timestamp() * 1000)
    end_ms = int(end_dt.timestamp() * 1000)
    components = ("east", "north", "up")

    dense_by_comp = {
        comp: await _load_dense_component(geosncl_list, comp, start_dt, end_dt, outlier_m=outlier_m)
        for comp in components
    }

    loop = asyncio.get_event_loop()

    def _decompose() -> tuple[dict[str, list[float]], dict[str, dict[str, np.ndarray]], dict[str, int]]:
        variance_explained: dict[str, list[float]] = {}
        residuals_by_comp: dict[str, dict[str, np.ndarray]] = {}
        n_complete_epochs: dict[str, int] = {}
        for comp in components:
            dense = dense_by_comp[comp]
            n_modes = min(n_modes_removed, len(geosncl_list))
            if method == "pca":
                pca_result = pca_mod.principal_component_analysis(dense, n_modes=n_modes)
                variance_explained[comp] = pca_result["variance_explained_pct"]
                residuals_by_comp[comp] = pca_mod.pca_common_mode_removed(dense, n_modes_removed=n_modes)
                n_complete_epochs[comp] = pca_result["n_complete_epochs"]
            else:
                kle_result = kle.karhunen_loeve(dense, n_modes=n_modes)
                variance_explained[comp] = kle_result["variance_explained_pct"]
                residuals_by_comp[comp] = kle.common_mode_removed(dense, n_modes_removed=n_modes)
        return variance_explained, residuals_by_comp, n_complete_epochs

    variance_explained, residuals_by_comp, n_complete_epochs = await loop.run_in_executor(_executor, _decompose)

    n_grid = max(0, (end_ms - start_ms) // 1000)
    grid_times = (start_ms + 1000 * np.arange(n_grid)) if n_grid else np.array([], dtype=np.int64)

    indices = np.arange(n_grid)
    factor = 1
    if downsample and n_grid > max_points:
        factor = max(1, n_grid // max_points)
        indices = indices[::factor][:max_points]

    def _nullable(arr: np.ndarray) -> list[float | None]:
        sub = arr[indices]
        return [None if np.isnan(v) else float(v) for v in sub]

    stations = [
        {
            "geosncl": g,
            "times": grid_times[indices].tolist(),
            "east":  _nullable(residuals_by_comp["east"][g]),
            "north": _nullable(residuals_by_comp["north"][g]),
            "up":    _nullable(residuals_by_comp["up"][g]),
            "downsampleFactor": factor,
        }
        for g in geosncl_list
    ]

    response: dict = {
        "stations": stations,
        "nModesRemoved": n_modes_removed,
        "method": method,
        "varianceExplainedPct": variance_explained,
    }
    if method == "pca":
        response["nCompleteEpochs"] = n_complete_epochs
    return JSONResponse(response)


# ── /api/fetch-missing ────────────────────────────────────────────────────────

def _missing_by_day(
    geosncls: list[str],
    start_date: dt.date,
    end_date: dt.date,
) -> dict[dt.date, list[str]]:
    """For each day in [start_date, end_date], return the geosncls that have no
    arrow file and are not already recorded in no_data.json for that day."""
    dd = _data_dir()
    result: dict[dt.date, list[str]] = {}
    for gs in geosncls:
        have = {d for d, _ in _file_index.get(gs, []) if start_date <= d <= end_date}
        no_data = _load_no_data_records(gs, dd)
        d = start_date
        while d <= end_date:
            if d not in have and d.isoformat() not in no_data:
                result.setdefault(d, []).append(gs)
            d += dt.timedelta(days=1)
    return result


def _sse(obj: dict) -> str:
    return f"data: {json.dumps(obj)}\n\n"


def _apply_stream_filters(
    geosncls: list[str],
    centers: list[str],
    sol_types: list[str],
) -> list[str]:
    """Keep geosncls whose center (2nd part) and sol-type (first 2 of 4th part)
    are in the given lists.  An empty filter list means 'accept all'."""
    if not centers and not sol_types:
        return geosncls
    fc, fs = set(centers), set(sol_types)
    out: list[str] = []
    for gs in geosncls:
        parts = gs.split(".")
        if len(parts) < 4:
            out.append(gs)
            continue
        if fc and parts[1] not in fc:
            continue
        if fs and parts[3][:2] not in fs:
            continue
        out.append(gs)
    return out


def _geosncl_edid_map() -> dict[str, str]:
    """Map geosncl -> edid across every station-list file.

    The positions API is queried by EDID (``stream_id``), so the fetch subprocess
    needs each stream's edid — not just its geosncl — or every request 422s
    (the API expects a ULID; the raw geosncl string doesn't parse as one).

    Only records with a genuine ``edid`` field contribute — no falling back
    to the geosncl itself for either side. That fallback used to let a
    stream list saved without edid "poison" the map with a bogus self-mapped
    entry (geosncl -> geosncl); since this scans files in alphabetical order
    and uses setdefault, whichever file came first alphabetically won
    regardless of whether it actually had a real edid — silently blocking a
    later, correct file from ever filling in the right value.
    """
    d = _stream_lists_dir()
    mapping: dict[str, str] = {}
    if not d.exists():
        return mapping
    for path in sorted(d.iterdir()):
        if path.suffix not in (".jsonl", ".json"):
            continue
        try:
            for rec in _read_stream_list_file(path):
                gs = rec.get("geosncl", "")
                eid = rec.get("edid", "")
                if gs and eid:
                    mapping.setdefault(gs, eid)
        except Exception:
            pass
    return mapping


async def _fetch_missing_events(
    requested: list[str],
    start_date: dt.date,
    end_date: dt.date,
    workers: int,
    edid_map: dict[str, str] | None = None,
):
    """Shared SSE generator: fetch every missing (geosncl, day) pair for
    *requested* over [start_date, end_date].  Yields ``data: {...}`` strings.

    *edid_map* maps geosncl -> edid so the fetch subprocess can query the API by
    EDID; a missing entry falls back to the geosncl string.
    """
    import tempfile

    edid_map = edid_map or {}

    # Compute exact (geosncl, day) pairs that need fetching
    by_day = _missing_by_day(requested, start_date, end_date)
    total_pairs = sum(len(v) for v in by_day.values())
    unique_gs = len({g for gs in by_day.values() for g in gs})
    already_done = len(requested) - unique_gs

    # Everything asked for, cached or not.  Cache hits are filtered out below
    # and never reach the fetch subprocess, so without carrying these counts
    # forward a mostly-cached run reads as a small fresh download and the
    # caching looks broken.
    n_days = (end_date - start_date).days + 1
    requested_pairs = len(requested) * n_days
    cached_pairs = requested_pairs - total_pairs

    if not by_day:
        yield _sse({"type": "log", "current": 0, "total": 0, "msg":
            f"{len(requested)} stream(s) × {n_days} day(s) = {requested_pairs} pair(s) — "
            f"all already present or previously attempted; nothing to fetch."})
        yield _sse({"type": "done", "code": 0, "current": 0, "total": 0})
        return

    sorted_days = sorted(by_day.keys())

    yield _sse({"type": "log", "current": 0, "total": len(sorted_days), "msg":
        f"{len(requested)} stream(s) × {n_days} day(s) = {requested_pairs} pair(s): "
        f"{cached_pairs} already cached, {total_pairs} to fetch "
        f"({unique_gs} stream(s) over {len(by_day)} day(s); {already_done} stream(s) complete)"})

    tf_path: str | None = None
    proc: asyncio.subprocess.Process | None = None
    errors = 0

    try:
        for i, day in enumerate(sorted_days):
            day_gs = sorted(by_day[day])
            day_str = day.isoformat()
            next_str = (day + dt.timedelta(days=1)).isoformat()

            # Pairs for this day that were already satisfied, so the subprocess
            # can report totals for the whole day rather than just its misses.
            day_precached = len(requested) - len(day_gs)

            yield _sse({"type": "log", "current": i + 1, "total": len(sorted_days), "msg":
                f"[{i + 1}/{len(sorted_days)}] {day_str} — {len(day_gs)} to fetch, "
                f"{day_precached} cached, {len(requested)} total"})

            with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as tf:
                for g in day_gs:
                    tf.write(json.dumps({"geosncl": g, "edid": edid_map.get(g, g)}) + "\n")
                tf_path = tf.name

            cmd = [
                sys.executable, "-m", "earthscope_positions.fetch.positions_fetch",
                "--list", tf_path,
                "--start", day_str, "--end", next_str,
                "--workers", str(workers),
                "--precached", str(day_precached),
            ]
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                cwd=str(_project_root()),
                env=_child_env(),
            )
            async for raw in proc.stdout:  # type: ignore[union-attr]
                line = raw.decode(errors="replace").rstrip()
                if line:
                    yield _sse({"type": "log", "msg": line})
            await proc.wait()
            ret = proc.returncode
            proc = None

            pathlib.Path(tf_path).unlink(missing_ok=True)
            tf_path = None

            if ret != 0:
                errors += 1
                yield _sse({"type": "error", "msg": f"Fetch for {day_str} exited with code {ret}"})

    except asyncio.CancelledError:
        if proc and proc.returncode is None:
            proc.terminate()
        asyncio.create_task(_refresh_index())
        yield _sse({"type": "done", "code": 1, "msg": "Canceled."})
        return
    except Exception as exc:
        asyncio.create_task(_refresh_index())
        yield _sse({"type": "error", "msg": str(exc)})
        yield _sse({"type": "done", "code": 1})
        return
    finally:
        if tf_path:
            pathlib.Path(tf_path).unlink(missing_ok=True)

    # Refresh the in-memory index so downstream pages immediately see new files
    yield _sse({"type": "log", "msg": "Updating file index…"})
    await _refresh_index()
    code = 0 if errors == 0 else 1
    yield _sse({"type": "done", "code": code,
                "current": len(sorted_days), "total": len(sorted_days),
                "msg": "Completed. File index updated." if code == 0
                       else f"Completed with {errors} day(s) having fetch errors."})


def _resolve_list_geosncls(name: str) -> list[str]:
    """Return geosncls for a saved list name (empty if not found/unreadable)."""
    sl_dir = _stream_lists_dir()
    list_path = sl_dir / f"{name}.jsonl"
    if not list_path.exists():
        list_path = sl_dir / f"{name}.json"
    if not list_path.exists():
        return []
    try:
        records = _read_stream_list_file(list_path)
        return [g for rec in records if (g := (rec.get("geosncl") or rec.get("edid", "")))]
    except Exception:
        return []


@app.get("/api/fetch-missing")
async def api_fetch_missing(
    list: str = Query("all"),
    start: str = Query(...),
    end: str = Query(...),
    workers: int = Query(10, ge=1, le=50),
    geosncls: str = Query(""),  # comma-separated; overrides list when provided
) -> StreamingResponse:
    async def generate():
        try:
            start_date = dt.date.fromisoformat(start)
            end_date = dt.date.fromisoformat(end)
        except ValueError:
            yield _sse({"type": "error", "msg": "Invalid date format. Use YYYY-MM-DD."})
            yield _sse({"type": "done", "code": 1})
            return

        if geosncls.strip():
            requested = [g.strip() for g in geosncls.split(",") if g.strip()]
        elif list == "all":
            yield _sse({"type": "error", "msg": "No geosncls provided."})
            yield _sse({"type": "done", "code": 1})
            return
        else:
            requested = _resolve_list_geosncls(list)
            if not requested:
                yield _sse({"type": "error", "msg": f"Station list not found or empty: {list}"})
                yield _sse({"type": "done", "code": 1})
                return

        async for chunk in _fetch_missing_events(
            requested, start_date, end_date, workers, _geosncl_edid_map()
        ):
            yield chunk

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


class _FetchMissingBody(BaseModel):
    lists: list[str] = []
    geosncls: list[str] = []
    filter_centers: list[str] = []
    filter_sol_types: list[str] = []
    start: str
    end: str
    workers: int = 10


@app.post("/api/fetch-missing")
async def api_fetch_missing_post(body: _FetchMissingBody) -> StreamingResponse:
    """POST variant of fetch-missing that resolves station lists + stream filters
    server-side (avoids huge query strings for large selections)."""
    async def generate():
        try:
            start_date = dt.date.fromisoformat(body.start)
            end_date = dt.date.fromisoformat(body.end)
        except ValueError:
            yield _sse({"type": "error", "msg": "Invalid date format. Use YYYY-MM-DD."})
            yield _sse({"type": "done", "code": 1})
            return

        workers = max(1, min(50, body.workers))
        requested_set: set[str] = {g for g in body.geosncls if g}
        for name in body.lists:
            requested_set.update(_resolve_list_geosncls(name))
        requested = _apply_stream_filters(
            sorted(requested_set), body.filter_centers, body.filter_sol_types
        )
        if not requested:
            yield _sse({"type": "error", "msg": "No stations selected."})
            yield _sse({"type": "done", "code": 1})
            return

        async for chunk in _fetch_missing_events(
            requested, start_date, end_date, workers, _geosncl_edid_map()
        ):
            yield chunk

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── Export / convert (Arrow → MiniSEED / GeoJSON) ──────────────────────────────

_EXPORT_SPEC_FILES = {
    "miniseed": "miniseed_path_spec.toml",
    "geojson":  "geojson_path_spec.toml",
}


def _export_spec_path(fmt: str) -> pathlib.Path | None:
    """The editable path-spec TOML for *fmt*, seeding it from the bundled
    template (into <data-directory>/resources/) if it doesn't exist yet."""
    name = _EXPORT_SPEC_FILES.get(fmt)
    return paths.ensure_resource(name) if name else None


@app.get("/api/export/spec")
async def api_export_get_spec(format: str = Query(...)) -> JSONResponse:
    """Return the editable path-spec TOML for the given export format."""
    path = _export_spec_path(format)
    if path is None:
        return JSONResponse({"error": "Invalid format"}, status_code=400)
    content = path.read_text(encoding="utf-8") if path.exists() else ""
    return JSONResponse({"format": format, "path": str(path.name), "content": content})


class _ExportSpecBody(BaseModel):
    format: str
    content: str


@app.put("/api/export/spec", response_model=None)
async def api_export_put_spec(body: _ExportSpecBody) -> JSONResponse:
    """Save the edited path-spec TOML (controls the output directory structure)."""
    path = _export_spec_path(body.format)
    if path is None:
        return JSONResponse({"error": "Invalid format"}, status_code=400)
    # Validate it parses as TOML before overwriting.
    try:
        import tomllib
        tomllib.loads(body.content)
    except Exception as exc:
        return JSONResponse({"error": f"Invalid TOML: {exc}"}, status_code=400)
    path.write_text(body.content, encoding="utf-8")
    _log.info("[export] saved %s (%d bytes)", path.name, len(body.content))
    return JSONResponse({"ok": True, "path": path.name})


@app.get("/api/export/run")
async def api_export_run(
    format: str = Query(...),                 # "miniseed" | "geojson"
    lists: list[str] = Query([]),
    start: str = Query(...),
    end: str = Query(...),
    gj_format: str = Query("both"),           # geojson only: compact | full | both
    ms_version: int = Query(3),               # miniseed only: 3 (default) | 2
    force: bool = Query(False),
) -> StreamingResponse:
    """Run es-pos export <format> for the selected lists/date range, streaming logs."""
    async def generate():
        if format not in _EXPORT_SPEC_FILES:
            yield _sse({"type": "error", "msg": f"Invalid format: {format}"})
            yield _sse({"type": "done", "code": 1})
            return
        try:
            dt.date.fromisoformat(start)
            dt.date.fromisoformat(end)
        except ValueError:
            yield _sse({"type": "error", "msg": "Invalid date format. Use YYYY-MM-DD."})
            yield _sse({"type": "done", "code": 1})
            return
        if format == "miniseed" and ms_version not in (2, 3):
            yield _sse({"type": "error",
                        "msg": f"Invalid MiniSEED version: {ms_version} (use 2 or 3)."})
            yield _sse({"type": "done", "code": 1})
            return
        sel = [l for l in lists if l and l != "all"]
        if not sel:
            yield _sse({"type": "error", "msg": "Select at least one station list."})
            yield _sse({"type": "done", "code": 1})
            return

        cmd = [sys.executable, "-m", "earthscope_positions.es_pos", "export", format]
        for l in sel:
            cmd += ["-i", l]
        cmd += ["--start-time", start, "--stop-time", end]
        if format == "geojson":
            cmd += ["--format", gj_format]
        if format == "miniseed":
            cmd += ["--format-version", str(ms_version)]
        if force:
            cmd += ["--force"]

        yield _sse({"type": "log", "msg": "es-pos " + " ".join(cmd[3:])})
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=str(_project_root()),
            env=_child_env(),
        )
        try:
            async for raw in proc.stdout:  # type: ignore[union-attr]
                line = raw.decode(errors="replace").rstrip()
                if line:
                    yield _sse({"type": "log", "msg": line})
            await proc.wait()
        except asyncio.CancelledError:
            if proc.returncode is None:
                proc.terminate()
            yield _sse({"type": "done", "code": 1, "msg": "Canceled."})
            return
        code = proc.returncode or 0
        yield _sse({"type": "done", "code": code,
                    "msg": "Done." if code == 0 else f"Export exited with code {code}"})

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── Plots file browser API ───────────────────────────────────────────────────

def _plots_root() -> pathlib.Path:
    return paths.plots_dir()


def _safe_plots_path(rel: str) -> pathlib.Path | None:
    """Resolve *rel* inside the plots root, refusing path-traversal attempts."""
    root = _plots_root().resolve()
    try:
        candidate = (root / rel.lstrip("/")).resolve()
    except Exception:
        return None
    if not str(candidate).startswith(str(root)):
        return None
    return candidate


class _SavePlotBody(BaseModel):
    filename: str
    data_url: str  # "data:image/png;base64,...."
    folder: str = "positions"  # slash-separated relative path under data/plots/, e.g. "coherence" or "positions/kle"


@app.post("/api/plots/save")
async def api_plots_save(body: _SavePlotBody) -> JSONResponse:
    """Save a client-rendered PNG under data/plots/<folder>/ (shows in File Plots)."""
    import base64

    name = pathlib.Path(body.filename).name  # strip any directory components
    if not name:
        return JSONResponse({"error": "Invalid filename"}, status_code=400)
    if not name.lower().endswith(".png"):
        name += ".png"

    payload = body.data_url
    if "," in payload:
        payload = payload.split(",", 1)[1]
    try:
        raw = base64.b64decode(payload)
    except Exception:
        return JSONResponse({"error": "Invalid image data"}, status_code=400)

    segments = [re.sub(r"[^A-Za-z0-9_-]", "", seg)[:40] for seg in body.folder.split("/")]
    segments = [s for s in segments if s] or ["positions"]
    out_dir = _plots_root()
    for seg in segments:
        out_dir = out_dir / seg
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / name
    out_path.write_bytes(raw)
    rel = out_path.relative_to(_plots_root())
    _log.info("[plots] saved positions plot %s (%d bytes)", rel, len(raw))
    return JSONResponse({"path": str(rel), "name": name})


@app.get("/api/plots/list")
async def api_plots_list(path: str = "") -> JSONResponse:
    """List directory entries under data/plots/.

    Returns JSON:  {"path": "...", "entries": [{"name": ..., "type": "dir"|"file", "path": ...}]}
    """
    target = _safe_plots_path(path)
    if target is None or not target.exists() or not target.is_dir():
        return JSONResponse({"error": "Not found"}, status_code=404)

    root = _plots_root().resolve()
    entries = []
    for child in sorted(target.iterdir(), key=lambda p: (p.is_file(), p.name.lower())):
        rel = str(child.resolve().relative_to(root))
        entries.append({
            "name": child.name,
            "type": "file" if child.is_file() else "dir",
            "path": rel,
        })
    return JSONResponse({"path": path, "entries": entries})


@app.get("/api/plots/img", response_model=None)
async def api_plots_img(path: str) -> FileResponse | JSONResponse:
    """Serve an image file from data/plots/."""
    target = _safe_plots_path(path)
    if target is None or not target.exists() or not target.is_file():
        return JSONResponse({"error": "Not found"}, status_code=404)
    suffix = target.suffix.lower()
    media = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
             "svg": "image/svg+xml", "gif": "image/gif"}.get(suffix[1:], "application/octet-stream")
    return FileResponse(target, media_type=media)


# ── /api/config (read-only mirror of `es-pos config show`) ───────────────────

@app.get("/api/config/data-directory")
async def api_config_data_directory() -> JSONResponse:
    """The resolved data directory and how it was decided.

    Distinct from /api/config, which reports the server's own host/port.

    Read-only on purpose.  Switching directories mid-session would leave every
    open tab pointing at a tree that no longer backs them, and the running
    server caches its resolution per process — so the switch belongs to
    `es-pos config use-data-dir`, before the server starts.
    """
    resolved = paths.base_dir()
    source = paths.base_dir_source()
    configured = paths.configured_data_dir()

    known = []
    for entry in paths.known_data_dirs():
        known.append({
            "path": str(entry),
            "active": entry == resolved,
            "exists": entry.exists(),
        })

    subdirs = []
    for label, getter in (
        ("arrow", paths.arrow_dir),
        ("stream-lists", paths.stream_lists_dir),
        ("station-lists", paths.station_lists_dir),
        ("plots", paths.plots_dir),
        ("resources", paths.resources_dir),
    ):
        d = getter()
        count = None
        if d.is_dir():
            try:
                count = sum(1 for _ in d.iterdir())
            except OSError:
                count = None
        subdirs.append({"name": label, "path": str(d),
                        "exists": d.is_dir(), "entries": count})

    # Inside a container the resolved path is the *container* path; on its own
    # that is confusing, since it does not exist on the host.  es-pos-docker.sh
    # passes the host side of the bind mount so both ends can be shown.
    host_data_dir = os.environ.get(paths.HOST_DATA_DIR_ENV_VAR) or None
    in_docker = paths.in_container() or bool(host_data_dir)
    persistent = paths.data_dir_is_persistent(resolved) if in_docker else None

    return JSONResponse({
        "data_directory": str(resolved),
        "exists": resolved.exists(),
        "source": source,
        "in_docker": in_docker,
        "host_data_directory": host_data_dir,
        "data_persistent": persistent,
        "launched_by_script": bool(host_data_dir),
        "source_label": {
            "env": f"{paths.ENV_VAR} environment variable",
            "config": "config file",
            "prompt": "answered at the first-run prompt",
            "default": "built-in default (nothing configured)",
        }.get(source, source),
        "config_file": str(paths.config_path()),
        "config_file_exists": paths.config_path().exists(),
        "configured_data_directory": str(configured) if configured else None,
        "env_var": paths.ENV_VAR,
        "env_value": os.environ.get(paths.ENV_VAR),
        "mismatch": configured is not None and configured != resolved,
        "known_data_directories": known,
        "subdirectories": subdirs,
    })


# ── /api/files (File Explorer — rooted at the data directory) ────────────────
#
# The Plots tab only ever showed <base>/plots.  The File Explorer is rooted at
# the data directory itself so the Arrow tree, the lists and the exports are all
# reachable from one place, with per-type summaries and file management.

_TEXT_EDIT_SUFFIXES = {".jsonl", ".json", ".csv", ".toml", ".txt", ".md"}
_IMAGE_MEDIA = {
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".svg": "image/svg+xml", ".gif": "image/gif",
}
_MSEED_SUFFIXES = {".mseed", ".ms", ".ms3", ".seed"}
#: Cap on bytes read back for text editing.  A stray multi-GB file would
#: otherwise be pulled into the browser whole.
_MAX_EDIT_BYTES = 8 * 1024 * 1024


def _files_root() -> pathlib.Path:
    return paths.base_dir()


def _safe_files_path(rel: str) -> pathlib.Path | None:
    """Resolve *rel* inside the data directory, refusing traversal.

    Uses ``is_relative_to`` rather than a string prefix test: with a root of
    ``/data``, a prefix test also accepts ``/data-backup``.
    """
    root = _files_root().resolve()
    try:
        candidate = (root / rel.lstrip("/")).resolve()
    except Exception:
        return None
    if candidate != root and not candidate.is_relative_to(root):
        return None
    return candidate


def _file_kind(path: pathlib.Path) -> str:
    """Coarse type used by the UI to pick an action set and a summary."""
    suffix = path.suffix.lower()
    if suffix == ".arrow":
        return "arrow"
    if suffix in _MSEED_SUFFIXES:
        return "miniseed"
    if suffix == ".geojson" or path.name.lower().endswith(".geojson.jsonl"):
        return "geojson"
    if suffix == ".jsonl":
        return "jsonl"
    if suffix in _IMAGE_MEDIA:
        return "image"
    if suffix == ".csv":
        return "csv"
    if suffix == ".toml":
        return "toml"
    if suffix in _TEXT_EDIT_SUFFIXES:
        return "text"
    return "other"


@app.get("/api/files/list")
async def api_files_list(path: str = "") -> JSONResponse:
    """List one directory under the data directory (lazily, one level at a time)."""
    target = _safe_files_path(path)
    if target is None or not target.exists() or not target.is_dir():
        return JSONResponse({"error": "Not found", "path": path}, status_code=404)

    root = _files_root().resolve()
    entries = []
    for child in sorted(target.iterdir(), key=lambda p: (p.is_file(), p.name.lower())):
        try:
            stat = child.stat()
        except OSError:
            continue
        is_file = child.is_file()
        entries.append({
            "name": child.name,
            "type": "file" if is_file else "dir",
            "path": str(child.resolve().relative_to(root)),
            "kind": _file_kind(child) if is_file else "dir",
            "size": stat.st_size if is_file else None,
            "mtime": stat.st_mtime,
        })
    return JSONResponse({"path": path, "root": str(root), "entries": entries})


def _summarize_arrow(target: pathlib.Path) -> dict:
    rows: list[tuple[str, str]] = []
    table = ipc.open_stream(target).read_all()
    rows.append(("Rows", f"{table.num_rows:,}"))
    rows.append(("Columns", str(table.num_columns)))
    if "time" in table.column_names and table.num_rows:
        times = table.column("time")
        t0 = pc.min(times).as_py()
        t1 = pc.max(times).as_py()
        if t0 is not None and t1 is not None:
            rows.append(("First sample", _ms_to_iso(t0)))
            rows.append(("Last sample", _ms_to_iso(t1)))
            span = (t1 - t0) / 1000.0
            rows.append(("Span", _fmt_duration(span)))
            if table.num_rows > 1:
                rows.append(("Nominal rate", f"{(table.num_rows - 1) / span:.3f} Hz"
                             if span > 0 else "—"))
    schema = [{"name": f.name, "type": str(f.type),
               "nulls": table.column(f.name).null_count}
              for f in table.schema]
    return {"rows": rows, "schema": schema}


def _summarize_miniseed(target: pathlib.Path) -> dict:
    from pymseed import MS3Record

    sids: dict[str, int] = {}
    n_records = 0
    n_samples = 0
    encodings: set[str] = set()
    versions: set[int] = set()
    start = end = None
    for rec in MS3Record.from_file(str(target)):
        n_records += 1
        n_samples += rec.samplecnt
        sids[rec.sourceid] = sids.get(rec.sourceid, 0) + rec.samplecnt
        encodings.add(rec.encoding_str())   # a method, not a property
        versions.add(rec.formatversion)
        s, e = rec.starttime, rec.endtime
        start = s if start is None else min(start, s)
        end = e if end is None else max(end, e)

    rows = [
        ("Records", f"{n_records:,}"),
        ("Samples", f"{n_samples:,}"),
        ("Channels", str(len(sids))),
        ("Format", ", ".join(f"miniSEED {v}" for v in sorted(versions)) or "—"),
        ("Encoding", ", ".join(sorted(encodings)) or "—"),
    ]
    if start is not None and end is not None:
        rows.append(("First sample", _ns_to_iso(start)))
        rows.append(("Last sample", _ns_to_iso(end)))
        rows.append(("Span", _fmt_duration((end - start) / 1e9)))
    channels = [{"name": sid, "samples": n} for sid, n in sorted(sids.items())]
    return {"rows": rows, "channels": channels}


def _summarize_geojson(target: pathlib.Path) -> dict:
    """Summarize a GeoJSON file: either a FeatureCollection or NDJSON features."""
    text = target.read_text(encoding="utf-8", errors="replace")
    features: list = []
    shape = "unknown"
    stripped = text.lstrip()
    if stripped.startswith("{"):
        try:
            doc = json.loads(text)
        except json.JSONDecodeError:
            doc = None
        if isinstance(doc, dict) and doc.get("type") == "FeatureCollection":
            features = doc.get("features") or []
            shape = "FeatureCollection"
        elif isinstance(doc, dict):
            features = [doc]
            shape = doc.get("type", "object")
    if not features:
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                features.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        if features:
            shape = "NDJSON (one feature per line)"

    times: list[str] = []
    stations: set[str] = set()
    lats: list[float] = []
    lons: list[float] = []
    for f in features:
        if not isinstance(f, dict):
            continue
        props = f.get("properties") or {}
        for key in ("time", "timestamp", "t"):
            if props.get(key):
                times.append(str(props[key]))
                break
        for key in ("station", "geosncl", "id"):
            if props.get(key):
                stations.add(str(props[key]))
                break
        geom = f.get("geometry") or {}
        coords = geom.get("coordinates")
        if isinstance(coords, list) and len(coords) >= 2:
            try:
                lons.append(float(coords[0]))
                lats.append(float(coords[1]))
            except (TypeError, ValueError):
                pass

    rows = [("Shape", shape), ("Features", f"{len(features):,}")]
    if stations:
        rows.append(("Stations", f"{len(stations):,}"))
    if times:
        rows.append(("First time", min(times)))
        rows.append(("Last time", max(times)))
    if lats and lons:
        rows.append(("Latitude range", f"{min(lats):.5f} … {max(lats):.5f}"))
        rows.append(("Longitude range", f"{min(lons):.5f} … {max(lons):.5f}"))
    return {"rows": rows, "stations": sorted(stations)[:200]}


def _summarize_jsonl(target: pathlib.Path) -> dict:
    """Summarize a JSONL list (stream lists, station lists, anything similar)."""
    lines = [l for l in target.read_text(encoding="utf-8", errors="replace").splitlines() if l.strip()]
    parsed: list[dict] = []
    bad = 0
    for line in lines:
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            bad += 1
            continue
        if isinstance(rec, dict):
            parsed.append(rec)

    keys: dict[str, int] = {}
    for rec in parsed:
        for k in rec:
            keys[k] = keys.get(k, 0) + 1

    rows = [("Entries", f"{len(lines):,}")]
    if bad:
        rows.append(("Unparseable lines", f"{bad:,}"))
    if keys:
        rows.append(("Fields", ", ".join(sorted(keys))))
    if "station" in keys:
        rows.insert(0, ("Kind", "station list"))
        stations = sorted({str(r.get("station", "")).upper() for r in parsed if r.get("station")})
        rows.append(("Unique stations", f"{len(stations):,}"))
    elif "geosncl" in keys:
        rows.insert(0, ("Kind", "stream list"))
        geos = [str(r["geosncl"]) for r in parsed if r.get("geosncl")]
        rows.append(("Unique streams", f"{len(set(geos)):,}"))
        rows.append(("Unique stations",
                     f"{len({g.split('.')[0].upper() for g in geos}):,}"))
        facilities = sorted({str(r.get("facility")) for r in parsed if r.get("facility")})
        if facilities:
            rows.append(("Facilities", ", ".join(facilities)))
    return {"rows": rows, "sample": lines[:10]}


def _summarize_csv(target: pathlib.Path) -> dict:
    """Summarize a CSV: shape, headers, and per-column detail where it is cheap.

    Numeric columns get a min/max range, which is what makes coordinates.csv --
    by far the most-edited CSV here -- readable at a glance.
    """
    import csv as _csv

    text = target.read_text(encoding="utf-8", errors="replace")
    reader = _csv.reader(io.StringIO(text))
    try:
        header = next(reader)
    except StopIteration:
        return {"rows": [("Rows", "0"), ("Note", "file is empty")]}
    body = [r for r in reader if any(cell.strip() for cell in r)]

    rows = [
        ("Rows", f"{len(body):,}"),
        ("Columns", str(len(header))),
        ("Headers", ", ".join(header)),
    ]

    ragged = sum(1 for r in body if len(r) != len(header))
    if ragged:
        rows.append(("Rows with wrong column count", f"{ragged:,}"))

    columns = []
    for i, name in enumerate(header):
        values = [r[i].strip() for r in body if i < len(r) and r[i].strip()]
        detail = ""
        numeric: list[float] = []
        for v in values:
            try:
                numeric.append(float(v))
            except ValueError:
                numeric = []
                break
        if numeric:
            detail = f"{min(numeric):.6g} … {max(numeric):.6g}"
        else:
            uniq = sorted(set(values))
            detail = (", ".join(uniq[:6]) + (" …" if len(uniq) > 6 else "")
                      if len(uniq) <= 20 else f"{len(uniq):,} distinct values")
        columns.append({
            "name": name,
            "filled": len(values),
            "blank": len(body) - len(values),
            "detail": detail,
        })

    return {
        "rows": rows,
        "columns": columns,
        "sample": [",".join(header)] + [",".join(r) for r in body[:5]],
    }


def _flatten_toml(value, prefix: str = "") -> list[tuple[str, str]]:
    """Flatten nested TOML tables into dotted key/value pairs for display."""
    out: list[tuple[str, str]] = []
    if isinstance(value, dict):
        for k, v in value.items():
            key = f"{prefix}.{k}" if prefix else str(k)
            out.extend(_flatten_toml(v, key))
    elif isinstance(value, list):
        out.append((prefix, f"[{len(value)} item(s)]" if len(value) > 4
                    else ", ".join(str(v) for v in value)))
    else:
        out.append((prefix, str(value)))
    return out


def _summarize_toml(target: pathlib.Path) -> dict:
    """Summarize a TOML file by flattening it to dotted keys.

    The TOML files here are the export path specs, so the useful view is simply
    every setting and its value -- with parse errors surfaced, since an invalid
    spec is exactly what someone opening this would be trying to find.
    """
    import tomllib

    text = target.read_text(encoding="utf-8", errors="replace")
    try:
        doc = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        return {"rows": [("Valid TOML", "no"), ("Parse error", str(exc))]}

    flat = _flatten_toml(doc)
    tables = [k for k, v in doc.items() if isinstance(v, dict)]
    rows = [
        ("Valid TOML", "yes"),
        ("Settings", f"{len(flat):,}"),
        ("Top-level keys", ", ".join(k for k, v in doc.items() if not isinstance(v, dict)) or "—"),
        ("Tables", ", ".join(f"[{t}]" for t in tables) or "—"),
        ("Comment lines", f"{sum(1 for l in text.splitlines() if l.strip().startswith('#')):,}"),
    ]
    return {"rows": rows, "settings": [{"key": k, "value": v} for k, v in flat]}


def _ms_to_iso(ms: int) -> str:
    return dt.datetime.fromtimestamp(ms / 1000, tz=dt.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ")


def _ns_to_iso(ns: int) -> str:
    return dt.datetime.fromtimestamp(ns / 1e9, tz=dt.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ")


def _fmt_duration(seconds: float) -> str:
    seconds = max(0.0, float(seconds))
    if seconds < 60:
        return f"{seconds:.1f} s"
    if seconds < 3600:
        return f"{seconds / 60:.1f} min"
    if seconds < 86400:
        return f"{seconds / 3600:.2f} h"
    return f"{seconds / 86400:.2f} d"


@app.get("/api/files/summary")
async def api_files_summary(path: str) -> JSONResponse:
    """Type-aware summary of one file's contents."""
    target = _safe_files_path(path)
    if target is None or not target.exists() or not target.is_file():
        return JSONResponse({"error": "Not found", "path": path}, status_code=404)

    kind = _file_kind(target)
    stat = target.stat()
    base = {
        "path": path,
        "name": target.name,
        "kind": kind,
        "size": stat.st_size,
        "mtime": stat.st_mtime,
        "editable": kind in ("jsonl", "geojson", "text", "csv", "toml")
                    and target.suffix.lower() in _TEXT_EDIT_SUFFIXES
                    and stat.st_size <= _MAX_EDIT_BYTES,
    }
    try:
        if kind == "arrow":
            base.update(_summarize_arrow(target))
        elif kind == "miniseed":
            base.update(await asyncio.get_event_loop().run_in_executor(
                None, _summarize_miniseed, target))
        elif kind == "geojson":
            base.update(_summarize_geojson(target))
        elif kind == "jsonl":
            base.update(_summarize_jsonl(target))
        elif kind == "csv":
            base.update(_summarize_csv(target))
        elif kind == "toml":
            base.update(_summarize_toml(target))
        else:
            base["rows"] = []
    except Exception as exc:
        # A summary failing must not make the file unmanageable -- the UI still
        # needs to offer rename/delete on something it cannot parse.
        base["rows"] = []
        base["error"] = f"{type(exc).__name__}: {exc}"
    return JSONResponse(base)


@app.get("/api/files/raw", response_model=None)
async def api_files_raw(path: str) -> JSONResponse:
    """Text contents of a file, for the in-page editor."""
    target = _safe_files_path(path)
    if target is None or not target.exists() or not target.is_file():
        return JSONResponse({"error": "Not found", "path": path}, status_code=404)
    if target.suffix.lower() not in _TEXT_EDIT_SUFFIXES:
        return JSONResponse({"error": f"{target.suffix} is not an editable text file"},
                            status_code=400)
    if target.stat().st_size > _MAX_EDIT_BYTES:
        return JSONResponse(
            {"error": f"File is larger than {_MAX_EDIT_BYTES // (1024 * 1024)} MB; "
                      f"edit it outside the browser."},
            status_code=413)
    return JSONResponse({"path": path, "name": target.name,
                         "content": target.read_text(encoding="utf-8", errors="replace")})


class _FileSaveBody(BaseModel):
    path: str
    content: str


@app.put("/api/files/raw", response_model=None)
async def api_files_save(body: _FileSaveBody) -> JSONResponse:
    """Overwrite a text file, validating JSONL line-by-line first."""
    target = _safe_files_path(body.path)
    if target is None or not target.exists() or not target.is_file():
        return JSONResponse({"error": "Not found", "path": body.path}, status_code=404)
    if target.suffix.lower() not in _TEXT_EDIT_SUFFIXES:
        return JSONResponse({"error": f"{target.suffix} is not an editable text file"},
                            status_code=400)
    if target.suffix.lower() == ".jsonl":
        for i, line in enumerate(body.content.splitlines(), start=1):
            if not line.strip():
                continue
            try:
                json.loads(line)
            except Exception as exc:
                return JSONResponse({"error": f"Invalid JSON on line {i}: {exc}"},
                                    status_code=400)
    content = body.content
    if content and not content.endswith("\n"):
        content += "\n"
    target.write_text(content, encoding="utf-8")
    _log.info("[files] saved %s (%d bytes)", body.path, len(content))
    return JSONResponse({"ok": True, "path": body.path, "bytes": len(content)})


class _FileRenameBody(BaseModel):
    path: str
    name: str


@app.post("/api/files/rename", response_model=None)
async def api_files_rename(body: _FileRenameBody) -> JSONResponse:
    """Rename a file in place (new name only — this does not move it)."""
    target = _safe_files_path(body.path)
    if target is None or not target.exists():
        return JSONResponse({"error": "Not found", "path": body.path}, status_code=404)
    new_name = pathlib.Path(body.name.strip()).name   # no directory components
    if not new_name or new_name in (".", ".."):
        return JSONResponse({"error": "Invalid name"}, status_code=400)
    dest = target.parent / new_name
    if dest.exists():
        return JSONResponse({"error": f"{new_name} already exists"}, status_code=409)
    target.rename(dest)
    rel = str(dest.resolve().relative_to(_files_root().resolve()))
    _log.info("[files] renamed %s -> %s", body.path, rel)
    return JSONResponse({"ok": True, "path": rel, "name": new_name})


@app.delete("/api/files", response_model=None)
async def api_files_delete(path: str) -> JSONResponse:
    """Delete a single file.

    Files only: a recursive directory delete is far too easy to trigger by
    accident on a tree this size, and nothing in the UI needs it.
    """
    target = _safe_files_path(path)
    if target is None or not target.exists():
        return JSONResponse({"error": "Not found", "path": path}, status_code=404)
    if target.is_dir():
        return JSONResponse({"error": "Refusing to delete a directory"}, status_code=400)
    target.unlink()
    _log.info("[files] deleted %s", path)
    return JSONResponse({"ok": True, "path": path})


@app.get("/api/files/download", response_model=None)
async def api_files_download(path: str) -> FileResponse | JSONResponse:
    """Serve a file inline — used to render images in the explorer."""
    target = _safe_files_path(path)
    if target is None or not target.exists() or not target.is_file():
        return JSONResponse({"error": "Not found", "path": path}, status_code=404)
    media = _IMAGE_MEDIA.get(target.suffix.lower(), "application/octet-stream")
    return FileResponse(target, media_type=media)


# ── /api/station-builder ─────────────────────────────────────────────────────

def _stations_payload(geosncls) -> list[dict]:
    """Group geosncls by station FCID and attach coordinates (from coordinates.csv).

    Included stations are the union of (a) every station in the "all-stations"
    list and (b) any station with at least one stream — coordinates.csv is only
    consulted for lat/lon, not to decide which stations to include, since it
    also holds thousands of unrelated reference-file entries (GAGE/ShakeAlert/
    RTDB) that aren't part of the active real-time network.

    Returns [{"station": "P143", "lat": 38.76, "lon": -119.76, "streams": [...]}].
    """
    by_station: dict[str, list[str]] = {}
    for gs in geosncls:
        parts = gs.split(".")
        if not parts:
            continue
        station = parts[0].upper()
        by_station.setdefault(station, []).append(gs)

    coords = _station_builder_coords
    all_stations = set(by_station) | set(_stations_for_list("all-stations"))

    stations = []
    for station in sorted(all_stations):
        coord = coords.get(station) if coords else None
        stations.append({
            "station": station,
            "lat": coord.latitude if coord else None,
            "lon": coord.longitude if coord else None,
            "streams": sorted(by_station.get(station, [])),
        })
    return stations


@app.get("/api/station-builder/data")
async def api_station_builder_data() -> JSONResponse:
    """All known stations with coordinates and available geosncl streams.

    Streams are the union of every station-list file (data/stream-lists/) and
    everything already downloaded (the Arrow file index), so the map shows all
    unique station/streams — not just the ones that happen to have data on disk.

    Returns:
        {"stations": [{"station": "P143", "lat": 38.76, "lon": -119.76, "streams": [...]}]}
    """
    geosncls = sorted(set(_all_list_geosncls()) | set(_indexed_geosncls()))
    return JSONResponse({"stations": _stations_payload(geosncls)})


# ── /api/coordinates (editable station-coordinate file) ───────────────────────

from earthscope_positions import coordinates as _coords_mod  # noqa: E402


def _reload_coords() -> None:
    """Re-load the in-memory coordinate table used by the Station Builder map."""
    global _station_builder_coords
    try:
        from earthscope_positions.coordinates import Coordinates
        _station_builder_coords = Coordinates()
    except Exception as exc:  # pragma: no cover - defensive
        print(f"  coords   : reload failed ({exc})", file=sys.stderr)


class _CoordinatesBody(BaseModel):
    content: str


@app.get("/api/coordinates/raw")
async def api_coordinates_get() -> JSONResponse:
    """Return the current editable coordinates CSV text (seeding on first use).

    Reports the resolved path either way.  The file lives under the *data*
    directory, so "could not open it" is nearly always a data-directory
    question -- naming the path it tried turns that into a one-look diagnosis
    instead of a guess.
    """
    path = _coords_mod.data_csv_path()
    try:
        return JSONResponse({"content": _coords_mod.read_text(), "path": str(path)})
    except Exception as exc:
        return JSONResponse(
            {"error": f"{type(exc).__name__}: {exc}", "path": str(path)},
            status_code=500,
        )


@app.put("/api/coordinates/raw", response_model=None)
async def api_coordinates_put(body: _CoordinatesBody) -> JSONResponse:
    """Edit Coordinates: validate the edited CSV and replace the file."""
    try:
        count = _coords_mod.save_edited(body.content)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    except Exception as exc:  # pragma: no cover - defensive
        return JSONResponse({"error": str(exc)}, status_code=500)
    _reload_coords()
    return JSONResponse({"ok": True, "count": count})


@app.post("/api/coordinates/update", response_model=None)
async def api_coordinates_update(body: _CoordinatesBody) -> JSONResponse:
    """Update Coordinates: validate an uploaded CSV and merge it in (uploaded
    rows win on station matches; ``source`` defaults to 'user' when omitted)."""
    try:
        total, added, updated = _coords_mod.merge_upload(body.content)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    except Exception as exc:  # pragma: no cover - defensive
        return JSONResponse({"error": str(exc)}, status_code=500)
    _reload_coords()
    return JSONResponse({"ok": True, "total": total, "added": added, "updated": updated})


# ── /api/replay ──────────────────────────────────────────────────────────────

from earthscope_positions.replay import replay as _replay_mod  # noqa: E402


class _ReplayPreloadBody(BaseModel):
    stream_lists: list[str] = []
    all_stations: bool = False
    start_time: str = ""
    stop_time: str = ""
    filter_centers: list[str] = []
    filter_sol_types: list[str] = []
    time_scale: float = 1.0
    apply_latency: bool = True
    select_by_arrival: bool = False
    output_format: str = "compact"   # "compact" | "geojson"
    bootstrap_server: str = "localhost:9092"
    topic: str = "protected.gnss.positions.shakealert.geojson.compact"


def _replay_data_dir() -> pathlib.Path:
    return paths.arrow_dir()


def _parse_replay_dt(s: str) -> dt.datetime:
    """Parse YYYY-MM-DD or YYYY-MM-DDTHH:MM[:SS] into a UTC datetime."""
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d"):
        try:
            return dt.datetime.strptime(s.strip(), fmt).replace(tzinfo=_UTC)
        except ValueError:
            pass
    raise ValueError(s)


@app.post("/api/replay/preload", response_model=None)
async def api_replay_preload(body: _ReplayPreloadBody) -> JSONResponse:
    try:
        start_dt = _parse_replay_dt(body.start_time)
        stop_dt  = _parse_replay_dt(body.stop_time)
    except ValueError:
        return JSONResponse({"error": "Invalid datetime. Use YYYY-MM-DDTHH:MM or YYYY-MM-DD."}, status_code=400)
    if stop_dt < start_dt:
        return JSONResponse({"error": "stop_time must be >= start_time"}, status_code=400)
    start = start_dt.date()
    stop  = stop_dt.date()

    # Resolve geosncls
    if body.all_stations:
        geosncls = _indexed_geosncls()
    elif body.stream_lists:
        geosncl_set: set[str] = set()
        for lst in body.stream_lists:
            geosncl_set.update(_geosncls_for_list(lst))
        geosncls = sorted(geosncl_set)
    else:
        return JSONResponse({"error": "Specify stream_lists or all_stations=true"}, status_code=400)

    # Apply stream filters
    geosncls = _replay_mod.filter_geosncls(
        geosncls,
        body.filter_centers,
        body.filter_sol_types,
    )

    start_data_ms = int(start_dt.timestamp() * 1000)
    config = {
        "bootstrap_server": body.bootstrap_server,
        "topic":            body.topic,
        "time_scale":       body.time_scale,
        "apply_latency":    body.apply_latency,
        "select_by_arrival": body.select_by_arrival,
        "output_format":    "geojson" if body.output_format == "geojson" else "compact",
        "start_data_ms":    start_data_ms,
        # Intra-day data-time window (epoch ms) so a 2-minute selection replays
        # only those 2 minutes, not the whole day's file.
        "window_start_ms":  int(start_dt.timestamp() * 1000),
        "window_stop_ms":   int(stop_dt.timestamp() * 1000),
        "start_time":       body.start_time,
        "stop_time":        body.stop_time,
        "stream_lists":     body.stream_lists,
        "all_stations":     body.all_stations,
    }

    ok = _replay_mod.start_preload(geosncls, start, stop, _replay_data_dir(), config)
    if not ok:
        return JSONResponse({"error": "A replay is already in progress"}, status_code=409)
    return JSONResponse({"status": "preloading"})


@app.get("/api/replay/status")
async def api_replay_status() -> JSONResponse:
    # Drop the (potentially large) file list from the polled payload — the UI
    # only needs the count — so status stays lean at ~1 Hz polling.
    st = _replay_mod.get_state()
    files = st.get("files")
    if isinstance(files, list):
        st["files_count"] = len(files)
        st.pop("files", None)
    return JSONResponse(st)


@app.post("/api/replay/start", response_model=None)
async def api_replay_start() -> JSONResponse:
    """Start the currently-preloaded replay (no job_id required — for external curl triggers).

    Returns immediately: the replay's schedule is anchored to this request time,
    so the data timeline is synchronized to when the curl call was made.  The
    measured start→first-write delay is reported via /api/replay/status
    (startup_delay_ms) rather than by blocking here.
    """
    state = _replay_mod.get_state()
    status = state.get("status")
    if status not in ("running", "starting"):
        ok = _replay_mod.start_preloaded()
        if not ok:
            return JSONResponse(
                {"error": f"No preloaded replay ready (status={status!r})"},
                status_code=409,
            )
    s = _replay_mod.get_state()
    return JSONResponse({"status": "running", "start_requested_ms": s.get("start_requested_ms")})


@app.post("/api/replay/{job_id}/go", response_model=None)
async def api_replay_go(job_id: str) -> JSONResponse:
    ok = _replay_mod.start_replay(job_id)
    if not ok:
        state = _replay_mod.get_state()
        if state.get("status") == "preloaded" and state.get("job_id") != job_id:
            return JSONResponse({"error": "Job ID mismatch"}, status_code=403)
        return JSONResponse({"error": f"Cannot start: status={state.get('status')}"}, status_code=409)
    loop = asyncio.get_event_loop()
    timing = await loop.run_in_executor(None, _replay_mod.wait_first_write, 30.0)
    return JSONResponse({"status": "running", **timing})


@app.post("/api/replay/cancel", response_model=None)
async def api_replay_cancel() -> JSONResponse:
    ok = _replay_mod.cancel_replay()
    if not ok:
        return JSONResponse({"error": "Nothing to cancel"}, status_code=409)
    s = _replay_mod.get_state()
    return JSONResponse({
        "status": "canceling",
        "sent": s.get("sent", 0),
        "cancel_requested_ms": s.get("cancel_requested_ms"),
        "startup_delay_ms": s.get("startup_delay_ms"),
    })


@app.post("/api/replay/reset", response_model=None)
async def api_replay_reset() -> JSONResponse:
    _replay_mod.reset()
    return JSONResponse({"status": "idle"})


# ── /api/readme ───────────────────────────────────────────────────────────────

@app.get("/api/readme")
async def api_readme() -> JSONResponse:
    path = _project_root() / "README.md"
    if not path.exists():
        return JSONResponse({"content": ""})
    return JSONResponse({"content": path.read_text(encoding="utf-8")})


def _all_list_geosncls() -> list[str]:
    """Return a deduplicated sorted list of all geosncls from every station list file."""
    d = _stream_lists_dir()
    if not d.exists():
        return []
    seen: set[str] = set()
    for path in sorted(d.iterdir()):
        if path.suffix not in (".jsonl", ".json"):
            continue
        try:
            records = _read_stream_list_file(path)
            for rec in records:
                g = rec.get("geosncl") or rec.get("edid", "")
                if g:
                    seen.add(g)
        except Exception:
            pass
    return sorted(seen)


# ── /api/ppsd ─────────────────────────────────────────────────────────────────

_SOL_LABELS: dict[str, str] = {
    "0": "CWU", "1": "PIVOT", "2": "RTNet", "3": "Septa", "4": "RTX", "5": "Net", "6": "JPL",
}
_TYPE_LABELS: dict[str, str] = {
    "0": "Fast", "1": "RTK", "2": "Compl", "3": "F+C",
}
_PPP_SOL_LABELS: dict[str, str] = {
    "0": "CWU Fastlane", "1": "Trimble PIVOT", "2": "RTNet",
    "3": "Septentrio", "4": "RTX on-board", "5": "Network", "6": "JPL PPP",
}
_CENTER_LABELS: dict[str, str] = {
    "PB": "EarthScope", "PW": "CWU", "NC": "USGS Menlo Park", "BK": "UCB", "CI": "USGS Pasadena",
}


def _sol_type_label(code: str) -> str:
    """Return a readable label for a 2-char sol_type code like '30' → 'Septa Fast'."""
    sol = _SOL_LABELS.get(code[0], code[0]) if code else ""
    typ = _TYPE_LABELS.get(code[1], code[1]) if len(code) > 1 else ""
    return f"{sol} {typ}".strip()


def _ppsd_group_key(gs: str, mode: str) -> str | None:
    if mode == "all":
        return "__all__"
    parts = gs.split(".")
    if len(parts) < 4:
        return None
    center = parts[1]
    loc = parts[3]
    sol_type = loc[:2]
    if mode == "by-center":
        return center
    if mode == "by-solution":
        return sol_type
    if mode == "by-center-solution":
        return f"{center}\x00{sol_type}"
    return gs  # by-stream: key = geosncl itself


def _ppsd_group_label(key: str, mode: str) -> str:
    if mode == "all":
        return "All Stations"
    if mode == "by-center":
        return f"{key} ({_CENTER_LABELS.get(key, key)})"
    if mode == "by-solution":
        return f"Sol {key} ({_sol_type_label(key)})"
    if mode == "by-center-solution":
        c, st = key.split("\x00", 1)
        return f"{c}.{st} ({_CENTER_LABELS.get(c, c)} / {_sol_type_label(st)})"
    return key  # by-stream


def _ppsd_slugify(s: str) -> str:
    """Filesystem-safe plot name: lowercase, dashes, no underscores/parens."""
    s = s.lower().replace("(", "").replace(")", "")
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-") or "plot"


def _ppsd_label_and_slug(
    key: str,
    mode: str,
    sol_labels: dict[str, str],
    center_labels: dict[str, str],
) -> tuple[str, str]:
    """Return (title, filename-slug) for a PPSD group.

    Uses the caller-supplied stream-type enumeration labels (from the SPA's
    constants) for the solution type, so filenames track the enum names.
    """
    def sol(st: str) -> str:
        return sol_labels.get(st) or _sol_type_label(st)

    def ctr(c: str) -> str:
        return center_labels.get(c) or _CENTER_LABELS.get(c, c)

    if mode == "all":
        label = "All Stations"
    elif mode == "by-center":
        label = f"{key} {ctr(key)}"
    elif mode == "by-solution":
        label = sol(key)                       # e.g. "Onboard Sept"
    elif mode == "by-center-solution":
        c, st = key.split("\x00", 1)
        label = f"{c} {sol(st)}"
    else:
        label = key                            # by-stream: geosncl
    return label, _ppsd_slugify(label)


# ── PPSD common-mode removal ──────────────────────────────────────────────────
#
# The shared-noise source (clock/orbit products) is the same for every stream
# processed by the same center with the same solution/software — i.e. exactly
# the "by-center-solution" grouping, regardless of which *display* mode the
# PPSDs are being rendered in.  So CMR is always computed at that (center,
# sol_type) granularity, once per run, and the resulting residuals are then
# merged however the requested display `mode` groups streams together.
#
# This can't reuse the per-file sparse PPSD cache (*_ppsd.arrow* sidecars) —
# that cache holds the *raw* per-file histogram, reused across every possible
# grouping; a CMR residual is a different signal depending on which subgroup
# it was computed against, so writing it there would corrupt the raw cache
# for every other (non-CMR) read.  What *is* still cached is the expensive
# part — the raw arrow reads underlying the residual computation — via the
# existing `_table_cache` used by `_load_filtered_table`/`_load_dense_component`.

_PPSD_CMR_MIN_STREAMS = 2  # below this, a subgroup has no common mode to remove


async def _compute_ppsd_cmr_residuals(
    subgroup_members: dict[str, list[str]],
    start_dt: dt.datetime, end_dt: dt.datetime,
    n_modes_removed: int,
    method: str,
) -> dict[str, dict[str, dict[str, np.ndarray]]]:
    """Common-mode-removed E/N/U residuals for every (center, sol_type)
    subgroup with >= _PPSD_CMR_MIN_STREAMS members, over the full requested
    range, via either KLE or classical PCA (*method*).  Subgroups with a
    single member are omitted entirely — callers fall back to that member's
    raw per-file cache instead.  A PCA subgroup that never has every member
    overlapping simultaneously behaves the same way (pca_common_mode_removed
    returns the residual unchanged), so it doesn't need special-casing here.

    Returns {subgroup_key: {component: {geosncl: residual_array}}}.
    """
    from earthscope_positions.analysis import kle as kle_mod
    from earthscope_positions.analysis import pca as pca_mod

    out: dict[str, dict[str, dict[str, np.ndarray]]] = {}
    for key, members in subgroup_members.items():
        if len(members) < _PPSD_CMR_MIN_STREAMS:
            continue
        out[key] = {}
        for comp in ("east", "north", "up"):
            dense = await _load_dense_component(members, comp, start_dt, end_dt)
            if method == "pca":
                out[key][comp] = pca_mod.pca_common_mode_removed(dense, n_modes_removed=n_modes_removed)
            else:
                out[key][comp] = kle_mod.common_mode_removed(dense, n_modes_removed=n_modes_removed)
    return out


@app.get("/api/ppsd/run")
async def api_ppsd_run(
    lists: list[str] = Query([]),
    start: str = Query(...),
    end: str = Query(...),
    mode: str = Query("by-stream"),
    centers: str = Query(""),    # comma-sep filter; empty = all
    sol_types: str = Query(""),  # comma-sep combined 2-char codes; empty = all
    sol_labels: str = Query(""),     # JSON {code: label} from the SPA enumeration
    center_labels: str = Query(""),  # JSON {code: label}
    cmr: bool = Query(False, description="Remove common mode(s) before computing"),
    cmr_method: str = Query("kle", pattern="^(kle|pca)$"),
    n_modes_removed: int = Query(1, ge=1, le=10),
) -> StreamingResponse:
    def _sse(obj: dict) -> str:
        return f"data: {json.dumps(obj)}\n\n"

    try:
        sol_label_map = json.loads(sol_labels) if sol_labels else {}
    except Exception:
        sol_label_map = {}
    try:
        center_label_map = json.loads(center_labels) if center_labels else {}
    except Exception:
        center_label_map = {}

    async def generate():
        if not lists:
            yield _sse({"type": "error", "msg": "Select at least one station list."})
            yield _sse({"type": "done", "code": 1})
            return

        try:
            start_date = dt.date.fromisoformat(start)
            end_date   = dt.date.fromisoformat(end)
        except ValueError:
            yield _sse({"type": "error", "msg": "Invalid date format. Use YYYY-MM-DD."})
            yield _sse({"type": "done", "code": 1})
            return

        center_f    = [c.strip() for c in centers.split(",")   if c.strip()]
        sol_type_f  = [s.strip() for s in sol_types.split(",") if s.strip()]

        # Resolve all geosncls from the selected lists
        geosncl_set: set[str] = set()
        for lst in lists:
            geosncl_set.update(_geosncls_for_list(lst))

        # Filter by center / sol_type (combined 2-char code)
        def _matches(gs: str) -> bool:
            parts = gs.split(".")
            if len(parts) < 4:
                return True
            c   = parts[1]
            loc = parts[3]
            st  = loc[:2]
            if center_f   and c  not in center_f:   return False
            if sol_type_f and st not in sol_type_f: return False
            return True

        filtered = sorted(g for g in geosncl_set if _matches(g))

        # Find arrow files in date range via the in-memory index
        gs_files: dict[str, list[pathlib.Path]] = {}
        for gs in filtered:
            files = sorted(
                e.arrow_path
                for d, e in _file_index.get(gs, [])
                if start_date <= d <= end_date
            )
            if files:
                gs_files[gs] = files

        if not gs_files:
            yield _sse({"type": "error", "msg": "No Arrow files found for the selected criteria and date range."})
            yield _sse({"type": "done", "code": 1})
            return

        # Build non-empty groups — skip combinations with zero files.  Each
        # group also tracks its member geosncls (not just their files) so the
        # CMR path below can route each stream to its (center, sol_type)
        # residual independently of how this display mode merges them.
        if mode == "by-stream":
            groups = [(gs, files, [gs]) for gs, files in sorted(gs_files.items())]
        else:
            group_map: dict[str, list[pathlib.Path]] = {}
            group_members: dict[str, list[str]] = {}
            skipped_geosncls: list[str] = []
            for gs, files in gs_files.items():
                key = _ppsd_group_key(gs, mode)
                if key is None:
                    skipped_geosncls.append(gs)
                    continue
                group_map.setdefault(key, []).extend(files)
                group_members.setdefault(key, []).append(gs)
            groups = [
                (k, sorted(group_map[k]), sorted(group_members[k]))
                for k in sorted(group_map)
            ]

        n_groups = len(groups)

        if n_groups == 0:
            yield _sse({"type": "error", "msg": "All groups are empty after filtering."})
            yield _sse({"type": "done", "code": 1})
            return

        from earthscope_positions.export import ppsd_writer

        all_files = sorted({f for _, files, _ in groups for f in files})
        yield _sse({"type": "log", "msg":
            f"{n_groups} group(s), {len(all_files)} file(s)  ({start} → {end})"
            + (f"  · common-mode removed ({cmr_method.upper()})" if cmr else "")})

        loop = asyncio.get_event_loop()
        output_root = paths.plots_dir() / "ppsd"
        date_range = f"{start}_{end}"
        written_total = 0

        # ── Common-mode removal precompute (once per run, shared by every
        # display group — see _compute_ppsd_cmr_residuals for why the
        # subgroup boundary is always by-center-solution) ──────────────────
        cmr_residuals: dict[str, dict[str, dict[str, np.ndarray]]] = {}
        if cmr:
            subgroup_members: dict[str, list[str]] = {}
            for gs in gs_files:
                skey = _ppsd_group_key(gs, "by-center-solution")
                if skey is not None:
                    subgroup_members.setdefault(skey, []).append(gs)
            n_multi = sum(1 for m in subgroup_members.values() if len(m) >= _PPSD_CMR_MIN_STREAMS)
            n_solo = len(subgroup_members) - n_multi
            yield _sse({"type": "log", "msg":
                f"Computing {cmr_method.upper()} common mode over {n_multi} center+solution subgroup(s)"
                + (f" ({n_solo} single-stream subgroup(s) use raw data — nothing to remove)" if n_solo else "")
                + "…"})
            start_analysis_dt = dt.datetime.combine(start_date, dt.time.min, tzinfo=_UTC)
            end_analysis_dt = dt.datetime.combine(end_date + dt.timedelta(days=1), dt.time.min, tzinfo=_UTC)
            cmr_residuals = await _compute_ppsd_cmr_residuals(
                subgroup_members, start_analysis_dt, end_analysis_dt, n_modes_removed, cmr_method,
            )

        for i, (key, files, member_geosncls) in enumerate(groups):
            label, slug = _ppsd_label_and_slug(key, mode, sol_label_map, center_label_map)
            if cmr:
                # Distinguish common-mode-removed output from raw runs of the
                # same group — otherwise they'd land in the same ppsd-<slug>/
                # folder with only the date range telling them apart.
                slug = f"{slug}-cmr-{cmr_method}-{n_modes_removed}"
                label = f"{label} (CMR: {cmr_method.upper()}×{n_modes_removed})"
            title_prefix = "" if mode == "by-stream" else "Combined"

            yield _sse({"type": "progress",
                        "msg": f"({i + 1}/{n_groups}) : Generating {label}",
                        "current": i + 1, "total": n_groups})

            if not cmr:
                # Unchanged raw path: per-file sparse cache, reused across runs.
                futs = [
                    asyncio.ensure_future(loop.run_in_executor(_ppsd_pool, ppsd_writer.ensure_ppsd_cache, f))
                    for f in files
                ]
                n_loaded = 0
                n_files = len(files)
                for coro in asyncio.as_completed(futs):
                    try:
                        await coro
                    except Exception as exc:
                        yield _sse({"type": "error", "msg": f"  cache error: {exc}"})
                    n_loaded += 1
                    yield _sse({"type": "log", "msg": f"\tLoaded {n_loaded} / {n_files}."})

                def _render(files=files, label=label, slug=slug, title_prefix=title_prefix):
                    from earthscope_positions.export import ppsd_writer as pw
                    return pw.write_ppsd_from_caches(
                        files, output_root,
                        label=label, mode=mode, date_range=date_range,
                        slug=slug, title_prefix=title_prefix,
                    )
            else:
                # CMR path: members whose (center, sol_type) subgroup had >= 2
                # streams use the precomputed residual directly (bypassing the
                # per-file cache — see _compute_ppsd_cmr_residuals); members in
                # a single-stream subgroup have nothing to remove and fall
                # back to the raw per-file cache, same as the non-CMR path.
                cmr_members = [
                    gs for gs in member_geosncls
                    if _ppsd_group_key(gs, "by-center-solution") in cmr_residuals
                ]
                fallback_members = [gs for gs in member_geosncls if gs not in cmr_members]
                fallback_files = [f for gs in fallback_members for f in gs_files.get(gs, [])]

                if fallback_files:
                    futs = [
                        asyncio.ensure_future(loop.run_in_executor(_ppsd_pool, ppsd_writer.ensure_ppsd_cache, f))
                        for f in fallback_files
                    ]
                    n_loaded = 0
                    n_files_fb = len(fallback_files)
                    for coro in asyncio.as_completed(futs):
                        try:
                            await coro
                        except Exception as exc:
                            yield _sse({"type": "error", "msg": f"  cache error: {exc}"})
                        n_loaded += 1
                        yield _sse({"type": "log", "msg": f"\tLoaded {n_loaded} / {n_files_fb} (raw fallback)."})

                yield _sse({"type": "log", "msg":
                    f"\t{len(cmr_members)} stream(s) common-mode removed, "
                    f"{len(fallback_members)} using raw data."})

                def _render(
                    member_geosncls=member_geosncls, cmr_members=cmr_members,
                    fallback_files=fallback_files, label=label, slug=slug,
                    title_prefix=title_prefix,
                ):
                    from earthscope_positions.export import ppsd_writer as pw

                    hist_e = np.zeros((pw.N_PERIOD_BINS, pw.N_POWER_BINS), dtype=np.int64)
                    hist_n = np.zeros((pw.N_PERIOD_BINS, pw.N_POWER_BINS), dtype=np.int64)
                    hist_u = np.zeros((pw.N_PERIOD_BINS, pw.N_POWER_BINS), dtype=np.int64)
                    total_frames = 0

                    for gs in cmr_members:
                        skey = _ppsd_group_key(gs, "by-center-solution")
                        for comp, hist in (("east", hist_e), ("north", hist_n), ("up", hist_u)):
                            arr = cmr_residuals.get(skey, {}).get(comp, {}).get(gs)
                            if arr is None:
                                continue
                            frames = pw.accumulate_ppsd(arr, hist)
                            if comp == "east":
                                total_frames += frames

                    if fallback_files:
                        tables = [t for f in fallback_files if (t := pw.load_ppsd_cache(f)) is not None]
                        if tables:
                            fb_e, fb_n, fb_u, fb_frames = pw.merge_sparse_tables(tables)
                            hist_e += fb_e
                            hist_n += fb_n
                            hist_u += fb_u
                            total_frames += fb_frames

                    if total_frames == 0:
                        return None

                    n_files_total = sum(len(gs_files.get(gs, [])) for gs in member_geosncls)
                    return pw.render_ppsd_from_histograms(
                        hist_e, hist_n, hist_u, total_frames, n_files_total,
                        output_root, label=label, mode=mode, date_range=date_range,
                        slug=slug, title_prefix=title_prefix,
                    )

            try:
                p: pathlib.Path | None = await loop.run_in_executor(_executor, _render)
                if p:
                    written_total += 1
                    # Path relative to the plots root, so the File Plots tab can
                    # open it directly (?path=...).
                    try:
                        rel = str(p.relative_to(_plots_root()))
                    except ValueError:
                        rel = str(p)
                    yield _sse({"type": "file", "path": rel, "label": label,
                                "current": i + 1, "total": n_groups})
                else:
                    yield _sse({"type": "log", "msg": f"  {label}: no valid data — skipped"})
            except Exception as exc:
                yield _sse({"type": "error", "msg": f"{label}: {exc}"})

        yield _sse({"type": "done", "code": 0, "msg": f"Done. {written_total} plot(s) written."})

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── SPA static file fallback ─────────────────────────────────────────────────

@app.get("/{full_path:path}", response_model=None)
async def serve_spa(full_path: str) -> FileResponse | JSONResponse:
    spa = _spa_dir()
    if not spa.exists():
        return JSONResponse(
            {"error": "SPA not built. Run: cd spa/spaGenerator && npm install && npm run build"},
            status_code=503,
        )
    candidate = spa / full_path
    if candidate.exists() and candidate.is_file():
        return FileResponse(candidate)

    # A request for a static asset (has a file extension, e.g. a hashed JS/CSS
    # chunk) that doesn't exist must 404 — NOT fall back to index.html.  After a
    # rebuild deletes old hashed chunks, an already-open tab requests them; if we
    # returned index.html the browser would try to run HTML as a JS module and
    # navigation would silently fail.  A clean 404 lets the client detect the
    # stale-build condition and reload.  SPA routes are extensionless, so this
    # only affects asset-like paths.
    last_segment = full_path.rsplit("/", 1)[-1]
    if full_path.startswith("assets/") or "." in last_segment:
        return JSONResponse({"error": "Not found"}, status_code=404)

    index = spa / "index.html"
    if index.exists():
        return FileResponse(index)
    return JSONResponse({"error": "SPA not built"}, status_code=503)

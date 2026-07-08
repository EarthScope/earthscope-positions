"""
FastAPI server for GNSS position data visualization.

Serves:
  /api/station-lists   list of station_list JSON file names
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
import io
import json
import logging
import pathlib
import re
import sys
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

_log = logging.getLogger(__name__)

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.ipc as ipc

from fastapi import FastAPI, Query, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

_UTC = dt.timezone.utc

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

_data_dir_override: pathlib.Path | None = None
SCAN_INTERVAL_S = 60  # seconds between background index refreshes

_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="completeness-gen")
_ppsd_pool = ThreadPoolExecutor(
    max_workers=20,
    thread_name_prefix="ppsd-cache",
)

# Loaded at startup for the station builder map endpoint
_station_builder_coords = None  # earthscope_positions.coordinates.Coordinates | None


def set_data_dir(path: pathlib.Path) -> None:
    global _data_dir_override
    _data_dir_override = path


def _project_root() -> pathlib.Path:
    return pathlib.Path(__file__).parent.parent.parent.parent


def _data_dir() -> pathlib.Path:
    return _data_dir_override or (_project_root() / "data" / "arrow")


def _station_lists_dir() -> pathlib.Path:
    return _project_root() / "data" / "station-lists"


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


def _list_station_list_names() -> list[str]:
    d = _station_lists_dir()
    if not d.exists():
        return []
    return sorted(p.stem for p in d.glob("*.jsonl"))


def _read_station_list_file(path: pathlib.Path) -> list[dict]:
    """Read a station list file in either JSONL or (legacy) JSON array format."""
    raw = path.read_bytes()
    if path.suffix == ".json":
        return json.loads(raw)
    return [json.loads(line) for line in raw.splitlines() if line.strip()]


def _geosncls_for_list(list_name: str) -> list[str]:
    """Return geosncls for a named list (or 'all'), filtered to what the index knows."""
    available = set(_indexed_geosncls())
    if list_name == "all":
        return sorted(available)
    d = _station_lists_dir()
    path = d / f"{list_name}.jsonl"
    if not path.exists():
        path = d / f"{list_name}.json"   # backward compat
        if not path.exists():
            return []
    try:
        records = _read_station_list_file(path)
    except Exception:
        return []
    result: list[str] = []
    for rec in records:
        g = rec.get("geosncl") or rec.get("edid", "")
        if g and g in available:
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


# ── /api/station-lists ───────────────────────────────────────────────────────

@app.get("/api/station-lists")
async def api_station_lists() -> dict:
    return {"lists": _list_station_list_names()}


@app.get("/api/station-lists/filter-options")
async def api_station_lists_filter_options(
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


@app.get("/api/station-lists/shakealert-datasource")
async def api_shakealert_datasource() -> StreamingResponse:
    """Run es-pos stations get datasource --network-name SHAKE:ShakeAlert -o ShakeAlert."""
    def _sse(obj: dict) -> str:
        return f"data: {json.dumps(obj)}\n\n"

    async def generate():
        cmd = [
            sys.executable, "-m", "earthscope_positions.es_pos",
            "stations", "get", "datasource",
            "--network-name", "SHAKE:ShakeAlert",
            "-o", "ShakeAlert",
        ]
        yield _sse({"type": "log", "msg":
            "es-pos stations get datasource --network-name SHAKE:ShakeAlert -o ShakeAlert"})
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=str(_project_root()),
        )
        async for raw in proc.stdout:  # type: ignore[union-attr]
            line = raw.decode(errors="replace").rstrip()
            if line:
                yield _sse({"type": "log", "msg": line})
        await proc.wait()
        if proc.returncode == 0:
            yield _sse({"type": "done", "code": 0,
                        "msg": "Saved ShakeAlert.jsonl. Reload station lists to use it."})
        else:
            yield _sse({"type": "done", "code": proc.returncode,
                        "msg": f"Command exited with code {proc.returncode}"})

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _fetch_url_sync(url: str) -> bytes:
    import urllib.request
    with urllib.request.urlopen(url, timeout=30) as r:
        return r.read()


@app.get("/api/station-lists/update-active-from-ncedc")
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

        chanfile_codes = sorted(set(re.findall(r'chanfile_(\w+)\.dat', html_bytes.decode(errors="replace"))))
        if not chanfile_codes:
            yield _sse({"type": "error", "msg": "No chanfile_XX.dat files found."})
            yield _sse({"type": "done", "code": 1})
            return

        yield _sse({"type": "log", "msg": f"Found {len(chanfile_codes)} chanfile(s): {', '.join(chanfile_codes)}"})

        # Build cross-reference from all existing station-list files
        yield _sse({"type": "log", "msg": "Cross-referencing existing station lists…"})
        all_records: dict[str, dict] = {}
        d = _station_lists_dir()
        for path in sorted(d.iterdir()):
            if path.suffix not in (".jsonl", ".json"):
                continue
            try:
                for rec in _read_station_list_file(path):
                    gs = rec.get("geosncl") or rec.get("edid", "")
                    if gs and gs not in all_records:
                        all_records[gs] = rec
            except Exception:
                pass
        yield _sse({"type": "log", "msg": f"  {len(all_records)} unique stream(s) in existing lists."})

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

            records: list[dict] = []
            found = 0
            for gs in sorted(geosncls):
                if gs in all_records:
                    records.append(all_records[gs])
                    found += 1
                else:
                    records.append({"geosncl": gs})
            yield _sse({"type": "log", "msg": f"  {found}/{len(geosncls)} matched in existing lists."})

            list_name = f"{center}-Active"
            d.mkdir(parents=True, exist_ok=True)
            out_path = d / f"{list_name}.jsonl"
            out_path.write_text(
                "\n".join(json.dumps(rec, ensure_ascii=False) for rec in records) + "\n",
                encoding="utf-8",
            )
            created.append(list_name)
            yield _sse({"type": "log", "msg": f"  → Saved {list_name}.jsonl ({len(records)} stream(s))"})

        yield _sse({"type": "done", "code": 0,
                    "msg": f"Done. Created/updated: {', '.join(created)}. Reload the page to see new lists."})

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/station-lists/{name}", response_model=None)
async def api_get_station_list(name: str) -> JSONResponse:
    name = name.strip()
    if not name or ".." in name or "/" in name or "\\" in name:
        return JSONResponse({"error": "Invalid list name"}, status_code=400)
    d = _station_lists_dir()
    path = d / f"{name}.jsonl"
    if not path.exists():
        path = d / f"{name}.json"        # backward compat
        if not path.exists():
            return JSONResponse({"error": "Not found"}, status_code=404)
    try:
        records = _read_station_list_file(path)
        geosncls = [
            rec.get("geosncl") or rec.get("edid", "")
            for rec in records
            if rec.get("geosncl") or rec.get("edid")
        ]
        return JSONResponse({"name": name, "geosncls": sorted(set(g for g in geosncls if g))})
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.delete("/api/station-lists/{name}", response_model=None)
async def api_delete_station_list(name: str) -> JSONResponse:
    name = name.strip()
    if not name or ".." in name or "/" in name or "\\" in name:
        return JSONResponse({"error": "Invalid list name"}, status_code=400)
    d = _station_lists_dir()
    for suffix in (".jsonl", ".json"):
        path = d / f"{name}{suffix}"
        if path.exists():
            path.unlink()
            _log.info("[station-lists] deleted %r", name)
            return JSONResponse({"deleted": name})
    return JSONResponse({"error": "Not found"}, status_code=404)


class _SaveListBody(BaseModel):
    geosncls: list[str]


@app.post("/api/station-lists/{name}", response_model=None)
async def api_save_station_list(name: str, body: _SaveListBody) -> dict:
    name = name.strip()
    if not name or ".." in name or "/" in name or "\\" in name:
        return JSONResponse({"error": "Invalid list name"}, status_code=400)
    d = _station_lists_dir()
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{name}.jsonl"
    lines = "\n".join(json.dumps({"geosncl": g}) for g in sorted(body.geosncls)) + "\n"
    path.write_text(lines)
    _log.info("[station-lists] saved %r (%d stations)", name, len(body.geosncls))
    return {"name": name, "count": len(body.geosncls)}


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
        entries = _entries_in_range(geosncl, start_dt, end_dt)
        tables = []
        for entry in entries:
            try:
                buf = io.BytesIO(entry.arrow_path.read_bytes())
                tables.append(ipc.open_stream(buf).read_all())
            except Exception:
                continue
        if not tables:
            return {"geosncl": geosncl, "times": [], "east": [], "north": [], "up": [],
                    "sigE": [], "sigN": [], "sigU": [], "downsampleFactor": 1}

        table = pa.concat_tables(tables)
        time_col = table.column("time")
        mask = pc.and_(
            pc.greater_equal(time_col, pa.scalar(start_ms, pa.int64())),
            pc.less(time_col, pa.scalar(end_ms, pa.int64())),
        )
        table = table.filter(mask).sort_by("time")

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


@app.get("/api/fetch-missing")
async def api_fetch_missing(
    list: str = Query("all"),
    start: str = Query(...),
    end: str = Query(...),
    workers: int = Query(10, ge=1, le=50),
    geosncls: str = Query(""),  # comma-separated; overrides list when provided
) -> StreamingResponse:
    def _sse(obj: dict) -> str:
        return f"data: {json.dumps(obj)}\n\n"

    async def generate():
        import tempfile

        try:
            start_date = dt.date.fromisoformat(start)
            end_date = dt.date.fromisoformat(end)
        except ValueError:
            yield _sse({"type": "error", "msg": "Invalid date format. Use YYYY-MM-DD."})
            yield _sse({"type": "done", "code": 1})
            return

        # Resolve the requested geosncl set
        if geosncls.strip():
            requested = [g.strip() for g in geosncls.split(",") if g.strip()]
        elif list == "all":
            yield _sse({"type": "error", "msg": "No geosncls provided."})
            yield _sse({"type": "done", "code": 1})
            return
        else:
            sl_dir = _station_lists_dir()
            list_path = sl_dir / f"{list}.jsonl"
            if not list_path.exists():
                list_path = sl_dir / f"{list}.json"
            if not list_path.exists():
                yield _sse({"type": "error", "msg": f"Station list not found: {list}.jsonl"})
                yield _sse({"type": "done", "code": 1})
                return
            try:
                records = _read_station_list_file(list_path)
                requested = [rec.get("geosncl") or rec.get("edid", "") for rec in records]
                requested = [g for g in requested if g]
            except Exception as exc:
                yield _sse({"type": "error", "msg": str(exc)})
                yield _sse({"type": "done", "code": 1})
                return

        # Compute exact (geosncl, day) pairs that need fetching
        by_day = _missing_by_day(requested, start_date, end_date)
        total_pairs = sum(len(v) for v in by_day.values())
        unique_gs = len({g for gs in by_day.values() for g in gs})
        already_done = len(requested) - unique_gs

        if not by_day:
            yield _sse({"type": "log", "msg":
                f"{len(requested)} station(s) — all data already present or previously attempted."})
            yield _sse({"type": "done", "code": 0})
            return

        yield _sse({"type": "log", "msg":
            f"{len(requested)} station(s): {already_done} complete, "
            f"{unique_gs} stream(s) × {len(by_day)} day(s) = {total_pairs} pair(s) to fetch"})

        sorted_days = sorted(by_day.keys())
        tf_path: str | None = None
        proc: asyncio.subprocess.Process | None = None
        errors = 0

        try:
            for i, day in enumerate(sorted_days):
                day_gs = sorted(by_day[day])
                day_str = day.isoformat()
                next_str = (day + dt.timedelta(days=1)).isoformat()

                yield _sse({"type": "log", "msg":
                    f"[{i + 1}/{len(sorted_days)}] {day_str} — {len(day_gs)} stream(s)"})

                with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as tf:
                    for g in day_gs:
                        tf.write(json.dumps({"geosncl": g}) + "\n")
                    tf_path = tf.name

                cmd = [
                    sys.executable, "-m", "earthscope_positions.fetch.positions_fetch",
                    "get", "-i", tf_path,
                    "--start", day_str, "--end", next_str,
                    "--workers", str(workers),
                ]
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT,
                    cwd=str(_project_root()),
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

        # Refresh the in-memory index so the completeness page immediately sees new files
        yield _sse({"type": "log", "msg": "Updating file index…"})
        await _refresh_index()
        code = 0 if errors == 0 else 1
        yield _sse({"type": "done", "code": code,
                    "msg": "Completed. File index updated." if code == 0
                           else f"Completed with {errors} day(s) having fetch errors."})

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── Plots file browser API ───────────────────────────────────────────────────

def _plots_root() -> pathlib.Path:
    return _project_root() / "data" / "plots"


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


# ── /api/station-builder ─────────────────────────────────────────────────────

@app.get("/api/station-builder/data")
async def api_station_builder_data() -> JSONResponse:
    """All indexed stations with coordinates and available geosncl streams.

    Returns:
        {"stations": [{"site": "P143", "lat": 38.76, "lon": -119.76, "streams": [...]}]}
    """
    geosncls = _indexed_geosncls()

    # Group by 4-char station FCID (first dot-segment of the geosncl)
    by_station: dict[str, list[str]] = {}
    for gs in geosncls:
        parts = gs.split(".")
        if not parts:
            continue
        site = parts[0].upper()
        by_station.setdefault(site, []).append(gs)

    coords = _station_builder_coords
    stations = []
    for site in sorted(by_station):
        coord = coords.get(site) if coords else None
        stations.append({
            "site": site,
            "lat": coord.latitude if coord else None,
            "lon": coord.longitude if coord else None,
            "streams": sorted(by_station[site]),
        })

    return JSONResponse({"stations": stations})


# ── /api/replay ──────────────────────────────────────────────────────────────

from earthscope_positions.replay import replay as _replay_mod  # noqa: E402


class _ReplayPreloadBody(BaseModel):
    station_lists: list[str] = []
    all_stations: bool = False
    start_time: str = ""
    stop_time: str = ""
    filter_centers: list[str] = []
    filter_sol_types: list[str] = []
    time_scale: float = 1.0
    apply_latency: bool = True
    bootstrap_server: str = "localhost:9092"
    topic: str = "protected.gnss.positions.shakealert.geojson.compact"


def _replay_data_dir() -> pathlib.Path:
    return _data_dir_override or (_project_root() / "data" / "arrow")


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
    elif body.station_lists:
        geosncl_set: set[str] = set()
        for lst in body.station_lists:
            geosncl_set.update(_geosncls_for_list(lst))
        geosncls = sorted(geosncl_set)
    else:
        return JSONResponse({"error": "Specify station_lists or all_stations=true"}, status_code=400)

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
        "start_data_ms":    start_data_ms,
        "start_time":       body.start_time,
        "stop_time":        body.stop_time,
        "station_lists":    body.station_lists,
        "all_stations":     body.all_stations,
    }

    ok = _replay_mod.start_preload(geosncls, start, stop, _replay_data_dir(), config)
    if not ok:
        return JSONResponse({"error": "A replay is already in progress"}, status_code=409)
    return JSONResponse({"status": "preloading"})


@app.get("/api/replay/status")
async def api_replay_status() -> JSONResponse:
    return JSONResponse(_replay_mod.get_state())


@app.post("/api/replay/start", response_model=None)
async def api_replay_start() -> JSONResponse:
    """Start the currently-preloaded replay (no job_id required — for external curl triggers)."""
    state = _replay_mod.get_state()
    status = state.get("status")
    if status == "running" or status == "starting":
        return JSONResponse({"status": "running", "job_id": state.get("job_id")})
    ok = _replay_mod.start_preloaded()
    if not ok:
        return JSONResponse(
            {"error": f"No preloaded replay ready (status={status!r})"},
            status_code=409,
        )
    return JSONResponse({"status": "running"})


@app.post("/api/replay/{job_id}/go", response_model=None)
async def api_replay_go(job_id: str) -> JSONResponse:
    ok = _replay_mod.start_replay(job_id)
    if not ok:
        state = _replay_mod.get_state()
        if state.get("status") == "preloaded" and state.get("job_id") != job_id:
            return JSONResponse({"error": "Job ID mismatch"}, status_code=403)
        return JSONResponse({"error": f"Cannot start: status={state.get('status')}"}, status_code=409)
    return JSONResponse({"status": "running"})


@app.post("/api/replay/cancel", response_model=None)
async def api_replay_cancel() -> JSONResponse:
    ok = _replay_mod.cancel_replay()
    if not ok:
        return JSONResponse({"error": "Nothing to cancel"}, status_code=409)
    return JSONResponse({"status": "canceling"})


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
    d = _station_lists_dir()
    if not d.exists():
        return []
    seen: set[str] = set()
    for path in sorted(d.iterdir()):
        if path.suffix not in (".jsonl", ".json"):
            continue
        try:
            records = _read_station_list_file(path)
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


@app.get("/api/ppsd/run")
async def api_ppsd_run(
    lists: list[str] = Query([]),
    start: str = Query(...),
    end: str = Query(...),
    mode: str = Query("by-stream"),
    centers: str = Query(""),    # comma-sep filter; empty = all
    sol_types: str = Query(""),  # comma-sep combined 2-char codes; empty = all
) -> StreamingResponse:
    def _sse(obj: dict) -> str:
        return f"data: {json.dumps(obj)}\n\n"

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

        # Build non-empty groups — skip combinations with zero files
        if mode == "by-stream":
            groups = [(gs, files) for gs, files in sorted(gs_files.items())]
        else:
            group_map: dict[str, list[pathlib.Path]] = {}
            skipped_geosncls: list[str] = []
            for gs, files in gs_files.items():
                key = _ppsd_group_key(gs, mode)
                if key is None:
                    skipped_geosncls.append(gs)
                    continue
                group_map.setdefault(key, []).extend(files)
            groups = [(k, sorted(v)) for k, v in sorted(group_map.items())]

        n_groups = len(groups)

        if n_groups == 0:
            yield _sse({"type": "error", "msg": "All groups are empty after filtering."})
            yield _sse({"type": "done", "code": 1})
            return

        from earthscope_positions.export import ppsd_writer

        all_files = sorted({f for _, files in groups for f in files})
        yield _sse({"type": "log", "msg":
            f"{n_groups} group(s), {len(all_files)} file(s)  ({start} → {end})"})

        loop = asyncio.get_event_loop()
        run_dir = _project_root() / "data" / "plots" / "ppsd" / f"{start}_{end}"
        written_total = 0

        for i, (key, files) in enumerate(groups):
            label = _ppsd_group_label(key, mode)
            title_prefix = "" if mode == "by-stream" else "Combined"

            yield _sse({"type": "progress",
                        "msg": f"({i + 1}/{n_groups}) : Generating {label}",
                        "current": i + 1, "total": n_groups})

            # Load / compute caches for this group in parallel (20 workers)
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

            def _render(files=files, label=label, title_prefix=title_prefix):
                from earthscope_positions.export import ppsd_writer as pw
                return pw.write_ppsd_from_caches(
                    files, run_dir,
                    label=label, title_prefix=title_prefix,
                )

            try:
                p: pathlib.Path | None = await loop.run_in_executor(_executor, _render)
                if p:
                    written_total += 1
                    try:
                        rel = str(p.relative_to(_project_root()))
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
    index = spa / "index.html"
    if index.exists():
        return FileResponse(index)
    return JSONResponse({"error": "SPA not built"}, status_code=503)

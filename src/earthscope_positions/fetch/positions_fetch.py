"""
positions_fetch — download GNSS PPP position data from the EarthScope API.

Sub-commands:
    get     Download position data for stations in a station list
    concat  Concatenate and deduplicate multiple Arrow files
"""

from __future__ import annotations

import argparse
import datetime as dt
import io
import os
import pathlib
import subprocess
import sys
import time
import queue
import threading
from typing import Optional

import orjson
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.ipc as ipc
import requests
from earthscope_sdk.config.models import Tokens

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_TOKENS_PATH = pathlib.Path.home() / ".earthscope" / "default" / "tokens.json"
_REFRESH_MARGIN = 60  # seconds before expiry to trigger refresh

_API_BASE = "https://api.earthscope.org/beta/data-products/gnss/positions/instantaneous/v2"
_REQUEST_TIMEOUT = 120  # seconds per API call
_LOCK_TTL = 120  # lock expiry in seconds (2 minutes)
_DEFAULT_WORKERS = 10

_NO_DATA_FILE = "no_data.jsonl"
_NO_DATA_FILE_LEGACY = "no_data.json"
_LOCK_FILE = ".lock"
_TS_FMT = "%Y%m%dT%H%M%SZ"  # compact UTC timestamp for filenames
_ERROR_LOG = "data/positions_errors.jsonl"  # relative to project root
_MAX_RETRIES = 2          # 5xx tasks are re-queued up to this many times
_DEFAULT_WORKERS = 20

_UTC = dt.timezone.utc


def _project_root() -> pathlib.Path:
    """Walk up from CWD to find the project root (directory containing pyproject.toml)."""
    for p in [pathlib.Path.cwd(), *pathlib.Path.cwd().parents]:
        if (p / "pyproject.toml").exists():
            return p
    return pathlib.Path.cwd()


def _data_root() -> pathlib.Path:
    return _project_root() / "data" / "arrow"

# ---------------------------------------------------------------------------
# Auth (mirrors station_list.py)
# ---------------------------------------------------------------------------


def _read_tokens() -> Tokens:
    try:
        raw = _TOKENS_PATH.read_bytes()
    except FileNotFoundError:
        sys.exit("No credentials found. Please authenticate: es user login")
    return Tokens.model_validate_json(raw)


def _ensure_token() -> str:
    tokens = _read_tokens()
    try:
        body = tokens.access_token_body
    except ValueError:
        body = None
    if body is not None and body.ttl.total_seconds() > _REFRESH_MARGIN:
        return tokens.access_token.get_secret_value()
    result = subprocess.run(
        ["es", "user", "refresh-access-token"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        sys.exit(f"Token refresh failed:\n  {result.stderr.strip()}")
    return _read_tokens().access_token.get_secret_value()


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------


def _geosncl_label(geosncl: str) -> str:
    """Return the bare station label, stripping any 'GEOSNCL:' prefix."""
    if geosncl.startswith("GEOSNCL:"):
        return geosncl[len("GEOSNCL:") :]
    return geosncl


def _geosncl_dir(geosncl: str) -> pathlib.Path:
    return _data_root() / _geosncl_label(geosncl)


def _arrow_path(
    geosncl_dir: pathlib.Path, start: dt.datetime, end: dt.datetime
) -> pathlib.Path:
    month_dir = geosncl_dir / start.strftime("%Y%m")
    label = geosncl_dir.name
    fname = f"{label}_{start.strftime(_TS_FMT)}_{end.strftime(_TS_FMT)}.arrow"
    return month_dir / fname


# ---------------------------------------------------------------------------
# Lock (timestamp-based, per GEOSNCL directory)
# ---------------------------------------------------------------------------


def _acquire_lock(geosncl_dir: pathlib.Path) -> None:
    """Spin-wait for any live lock on geosncl_dir, then atomically create one."""
    geosncl_dir.mkdir(parents=True, exist_ok=True)
    lock = geosncl_dir / _LOCK_FILE
    expiry_bytes = str(time.time() + _LOCK_TTL).encode()

    while True:
        if lock.exists():
            try:
                expiry = float(lock.read_text().strip())
                if time.time() < expiry:
                    time.sleep(1)
                    continue
                else:
                    lock.unlink(missing_ok=True)  # expired — clean up
            except (ValueError, OSError):
                pass

        # Atomic create (O_EXCL prevents two processes racing here)
        try:
            fd = os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, expiry_bytes)
            os.close(fd)
            return
        except FileExistsError:
            time.sleep(0.1)


def _release_lock(geosncl_dir: pathlib.Path) -> None:
    (geosncl_dir / _LOCK_FILE).unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# No-data marker
# ---------------------------------------------------------------------------


def _load_no_data(geosncl_dir: pathlib.Path) -> set[str]:
    """Return set of date strings (YYYY-MM-DD) that have been attempted (any result)."""
    dates: set[str] = set()
    jsonl = geosncl_dir / _NO_DATA_FILE
    if jsonl.exists():
        for line in jsonl.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = orjson.loads(line)
                if d := rec.get("date"):
                    dates.add(d)
            except Exception:
                pass
        return dates
    # Fall back to legacy format
    old = geosncl_dir / _NO_DATA_FILE_LEGACY
    if old.exists():
        try:
            return set(orjson.loads(old.read_bytes()).get("dates", []))
        except Exception:
            pass
    return dates


def _add_no_data(geosncl_dir: pathlib.Path, date_str: str, result: str = "no-data") -> None:
    """Append one attempt record to no_data.jsonl."""
    geosncl_dir.mkdir(parents=True, exist_ok=True)
    record = orjson.dumps({
        "date": date_str,
        "attempted_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "result": result,
    }).decode() + "\n"
    (geosncl_dir / _NO_DATA_FILE).open("a", encoding="utf-8").write(record)


def _remove_no_data(geosncl_dir: pathlib.Path, date_str: str) -> None:
    """Remove all entries for date_str from no_data.jsonl (and legacy file if present)."""
    jsonl = geosncl_dir / _NO_DATA_FILE
    if jsonl.exists():
        lines = [l for l in jsonl.read_text(encoding="utf-8").splitlines() if l.strip()]
        kept = []
        for line in lines:
            try:
                if orjson.loads(line).get("date") != date_str:
                    kept.append(line)
            except Exception:
                kept.append(line)
        if kept:
            jsonl.write_text("\n".join(kept) + "\n", encoding="utf-8")
        else:
            jsonl.unlink(missing_ok=True)
    old = geosncl_dir / _NO_DATA_FILE_LEGACY
    if old.exists():
        try:
            dates = set(orjson.loads(old.read_bytes()).get("dates", []))
            dates.discard(date_str)
            if dates:
                old.write_bytes(orjson.dumps({"dates": sorted(dates)}, option=orjson.OPT_INDENT_2))
            else:
                old.unlink(missing_ok=True)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Arrow I/O
# ---------------------------------------------------------------------------


def _read_arrow_bytes(content: bytes) -> Optional[pa.Table]:
    """Parse Arrow IPC bytes (file or stream). Returns None if empty or unreadable."""
    for opener in (ipc.open_file, ipc.open_stream):
        try:
            tbl = opener(io.BytesIO(content)).read_all()
            return tbl if tbl.num_rows > 0 else None
        except Exception:
            continue
    return None


def _concat_dedup(tables: list[pa.Table]) -> pa.Table:
    """Concatenate tables, sort by time, drop duplicate timestamps."""
    combined = pa.concat_tables(tables)
    if combined.num_rows == 0:
        return combined
    sorted_idx = pc.sort_indices(combined, sort_keys=[("time", "ascending")])
    sorted_tbl = combined.take(sorted_idx)
    times = sorted_tbl.column("time")
    # First row always kept; subsequent rows kept when time differs from previous
    is_new = pc.not_equal(times[1:], times[:-1])
    keep_mask = pa.concat_arrays([pa.array([True]), is_new])
    return sorted_tbl.filter(keep_mask)


# ---------------------------------------------------------------------------
# Time range utilities
# ---------------------------------------------------------------------------


def _parse_datetime(s: str) -> dt.datetime:
    """Parse ISO date or datetime string, returning UTC-aware datetime."""
    try:
        parsed = dt.datetime.fromisoformat(s)
    except ValueError:
        sys.exit(
            f"Cannot parse {s!r}. Use ISO 8601, e.g. '2025-01-01' or "
            "'2025-01-01T12:00:00Z'."
        )
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=_UTC)
    return parsed.astimezone(_UTC)


def _day_ranges(
    start: dt.datetime, end: dt.datetime
) -> list[tuple[dt.datetime, dt.datetime]]:
    """Split [start, end) into UTC-midnight-aligned segments (one per calendar day)."""
    ranges: list[tuple[dt.datetime, dt.datetime]] = []
    cursor = start.astimezone(_UTC)
    end = end.astimezone(_UTC)
    while cursor < end:
        next_midnight = (cursor + dt.timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        seg_end = min(next_midnight, end)
        ranges.append((cursor, seg_end))
        cursor = seg_end
    return ranges


# ---------------------------------------------------------------------------
# Error logging
# ---------------------------------------------------------------------------

_error_log_lock = threading.Lock()


def _log_error(geosncl: str, date_str: str, resp: "requests.Response") -> None:
    """Append one JSONL line per API error to data/positions_errors.jsonl."""
    try:
        body = resp.json()
    except Exception:
        body = resp.text[:500] if resp.text else None
    entry = {
        "geosncl": geosncl,
        "date": date_str,
        "status": resp.status_code,
        "body": body,
    }
    log_path = _project_root() / _ERROR_LOG
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with _error_log_lock:
        with log_path.open("ab") as f:
            f.write(orjson.dumps(entry) + b"\n")


# ---------------------------------------------------------------------------
# Single-day fetch
# ---------------------------------------------------------------------------


def _fetch_one_day(
    token: str,
    edid: str,
    geosncl: str,
    day_start: dt.datetime,
    day_end: dt.datetime,
    force: bool,
    redownload: bool,
) -> str:
    """
    Fetch one UTC-day segment of position data.

    Returns:
        'ok'             — data downloaded and written
        'skipped'        — arrow file already exists (cache hit)
        'no-data-cached' — day is in no_data.json (skipped without API call)
        'no-data'        — API returned no rows; no_data.json updated
        'error-NNN'      — HTTP error code NNN
    """
    gdir = _geosncl_dir(geosncl)
    date_str = day_start.strftime("%Y-%m-%d")
    out_path = _arrow_path(gdir, day_start, day_end)

    # --- cache checks ---
    if not redownload and out_path.exists():
        return "skipped"
    if not force and not redownload and date_str in _load_no_data(gdir):
        return "no-data-cached"

    # --- acquire lock, call API once, release lock immediately ---
    _acquire_lock(gdir)
    try:
        resp = requests.get(
            _API_BASE,
            params={
                "stream_id": edid,
                "start_datetime": day_start.isoformat(),
                "end_datetime": day_end.isoformat(),
            },
            headers={
                "accept": "application/vnd.apache.arrow.stream",
                "accept-encoding": "",
                "authorization": f"Bearer {token}",
            },
            timeout=_REQUEST_TIMEOUT,
        )
    finally:
        _release_lock(gdir)

    if resp.status_code == 200:
        tbl = _read_arrow_bytes(resp.content)
        if tbl is not None:
            if redownload and out_path.exists():
                out_path.unlink()
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_bytes(resp.content)
            if redownload:
                _remove_no_data(gdir, date_str)
            return "ok"
        # 200 but zero rows
        if redownload and out_path.exists():
            out_path.unlink()
        _add_no_data(gdir, date_str, "no-data")
        return "no-data"

    elif resp.status_code == 404:
        # Not found — definitively no data, record permanently.
        if redownload and out_path.exists():
            out_path.unlink()
        _add_no_data(gdir, date_str, "no-data")
        return "no-data"

    elif resp.status_code in (400, 422):
        # API rejected the request (stream may not exist for this date/center).
        # Permanent client error — record so we stop retrying, but flag as error.
        if redownload and out_path.exists():
            out_path.unlink()
        _add_no_data(gdir, date_str, f"error-{resp.status_code}")
        return "no-data"

    else:
        # Transient errors (5xx, 401/403 token expiry, …) — do NOT record in
        # no_data.json; leave the day eligible for retry.  Log for inspection.
        _log_error(geosncl, date_str, resp)
        return f"error-{resp.status_code}"


# ---------------------------------------------------------------------------
# Progress display
# ---------------------------------------------------------------------------


class _Progress:
    """Thread-safe in-place progress line printed to stderr."""

    def __init__(self, total: int) -> None:
        self.total = total
        self.ok = 0        # freshly downloaded
        self.cached = 0    # skipped — arrow file already present
        self.no_data = 0   # API returned nothing (new or previously known)
        self.failed = 0    # HTTP / parse error
        self._lock = threading.Lock()
        self._start = time.monotonic()
        self._last = "—"
        self._is_tty = sys.stderr.isatty()

    @property
    def done(self) -> int:
        return self.ok + self.cached + self.no_data + self.failed

    def update(self, status: str, label: str, day: "dt.date") -> None:
        with self._lock:
            if status == "ok":
                self.ok += 1
                tag = "ok"
            elif status == "skipped":
                self.cached += 1
                tag = "cached"
            elif status in ("no-data", "no-data-cached"):
                self.no_data += 1
                tag = "no-data"
            else:
                self.failed += 1
                tag = status  # e.g. "error-503"
            self._last = f"{tag:<12} {label}  {day}"
            self._render()

    def _render(self) -> None:
        done = self.done
        elapsed_s = time.monotonic() - self._start
        elapsed_m = elapsed_s / 60.0
        if done > 0 and elapsed_s > 0:
            eta_m = (self.total - done) / (done / elapsed_s) / 60.0
            eta_str = f"{eta_m:.0f}m"
        else:
            eta_str = "?m"

        line = (
            f"{done:>6}/{self.total}"
            f"  ok:{self.ok:>5}"
            f"  has-data:{self.cached:>5}"
            f"  no-data:{self.no_data:>5}"
            f"  failed:{self.failed:>4}"
            f"  elapsed:{elapsed_m:.0f}m"
            f"  ETA:{eta_str}"
            f"  {self._last}"
        )
        if self._is_tty:
            # Pad to 140 chars to overwrite any longer previous line
            print(f"\r{line:<140}", end="", file=sys.stderr, flush=True)
        else:
            print(line, file=sys.stderr, flush=True)

    def finish(self) -> None:
        with self._lock:
            self._render()
            if self._is_tty:
                print(file=sys.stderr)  # move past the \r line

    def summary(self) -> str:
        elapsed_m = (time.monotonic() - self._start) / 60.0
        return (
            f"{self.ok} downloaded, {self.cached} has-data, "
            f"{self.no_data} no-data, {self.failed} failed  "
            f"({elapsed_m:.1f} min)"
        )


# ---------------------------------------------------------------------------
# Parallel execution
# ---------------------------------------------------------------------------


def _run_parallel(
    all_tasks: list[tuple],
    n_workers: int,
    progress: _Progress,
) -> None:
    """
    Dispatch tasks across n_workers threads while ensuring at most one active
    download per station at a time.

    Workers attempt a non-blocking acquire on a per-station threading.Lock.
    If a station is busy they put the task back in the queue and pick the next
    available one, so all worker slots stay occupied with different stations
    rather than blocking behind each other.
    """
    if not all_tasks:
        return

    task_q: queue.Queue = queue.Queue()
    for t in all_tasks:
        task_q.put(t)

    # Per-station in-process locks (serialize within this process;
    # the file lock handles cross-process coordination)
    station_locks: dict[str, threading.Lock] = {}
    locks_guard = threading.Lock()

    def get_station_lock(label: str) -> threading.Lock:
        with locks_guard:
            if label not in station_locks:
                station_locks[label] = threading.Lock()
            return station_locks[label]

    results_lock = threading.Lock()
    remaining = [len(all_tasks)]

    def worker() -> None:
        while True:
            with results_lock:
                if remaining[0] == 0:
                    return

            try:
                task = task_q.get(timeout=0.5)
            except queue.Empty:
                continue

            token_v, edid, geosncl, ds, de, force, redownload, retries_left = task
            label = _geosncl_label(geosncl)
            station_lock = get_station_lock(label)

            if not station_lock.acquire(blocking=False):
                # Station busy — defer and pick the next task instead
                task_q.put(task)
                time.sleep(0.05)
                continue

            status = "error-exception"
            try:
                status = _fetch_one_day(token_v, edid, geosncl, ds, de, force, redownload)
            except Exception as exc:
                print(
                    f"  ERROR  {label}  {ds.date()}  ({exc})",
                    file=sys.stderr,
                )
            finally:
                station_lock.release()

            # Re-queue on transient 5xx without blocking — worker moves on immediately
            if status.startswith("error-5") and retries_left > 0:
                task_q.put((token_v, edid, geosncl, ds, de, force, redownload, retries_left - 1))
                continue

            progress.update(status, label, ds.date())
            with results_lock:
                remaining[0] -= 1

    threads = [
        threading.Thread(target=worker, daemon=True) for _ in range(n_workers)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()


# ---------------------------------------------------------------------------
# Station list loading
# ---------------------------------------------------------------------------


def _load_station_list(path_str: str) -> list[dict]:
    p = pathlib.Path(path_str)
    stem = p.stem if p.suffix in (".jsonl", ".json") else p.name
    sl = _project_root() / "data" / "station-lists"
    candidates = [
        p,
        p.parent / (stem + ".jsonl"),
        sl / p.name,
        sl / (stem + ".jsonl"),
        sl / (stem + ".json"),           # backward compat
    ]
    for c in dict.fromkeys(candidates):
        if c.exists():
            raw = c.read_bytes()
            if c.suffix == ".json":
                return orjson.loads(raw)
            return [orjson.loads(line) for line in raw.splitlines() if line.strip()]
    tried = ", ".join(str(c) for c in dict.fromkeys(candidates))
    sys.exit(f"Station list not found. Tried: {tried}")


# ---------------------------------------------------------------------------
# Command: get
# ---------------------------------------------------------------------------


def _cmd_get(args) -> None:
    # Parse time range
    if args.start:
        start = _parse_datetime(args.start)
    else:
        start = dt.datetime.now(_UTC).replace(hour=0, minute=0, second=0, microsecond=0)

    if args.end:
        end = _parse_datetime(args.end)
        if end <= start:
            sys.exit("--end must be after --start")
    else:
        end = start + dt.timedelta(days=1)

    # Load and deduplicate stations
    stations: list[dict] = []
    seen_edids: set[str] = set()
    for path_str in args.input:
        for rec in _load_station_list(path_str):
            edid = rec.get("edid") or rec.get("geosncl")
            if edid and edid not in seen_edids:
                seen_edids.add(edid)
                stations.append(rec)

    if not stations:
        sys.exit("No stations found in the provided station lists.")

    day_segs = _day_ranges(start, end)
    n_tasks = len(stations) * len(day_segs)
    print(
        f"{len(stations)} station(s), {len(day_segs)} day-segment(s), "
        f"{n_tasks} task(s)",
        file=sys.stderr,
    )

    token = _ensure_token()
    stations_sorted = sorted(stations, key=lambda r: r.get("geosncl") or r.get("edid", ""))
    all_tasks = [
        (token,
         rec.get("edid") or rec.get("geosncl"),
         rec.get("geosncl") or rec.get("edid", ""),
         ds, de, args.force, args.redownload, _MAX_RETRIES)
        for ds, de in day_segs
        for rec in stations_sorted
    ]
    progress = _Progress(len(all_tasks))
    _run_parallel(all_tasks, args.workers, progress)
    progress.finish()
    print(f"Done: {progress.summary()}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Command: concat
# ---------------------------------------------------------------------------


def _cmd_concat(args) -> None:
    paths = [pathlib.Path(p) for p in args.files]
    missing = [p for p in paths if not p.exists()]
    if missing:
        sys.exit(f"File(s) not found:\n  " + "\n  ".join(str(p) for p in missing))

    tables: list[pa.Table] = []
    for p in paths:
        try:
            with ipc.open_file(p) as f:
                tbl = f.read_all()
            if tbl.num_rows > 0:
                tables.append(tbl)
            else:
                print(f"  Skipping empty file: {p}", file=sys.stderr)
        except Exception as exc:
            print(f"  Warning: cannot read {p}: {exc}", file=sys.stderr)

    if not tables:
        sys.exit("No valid rows found in input files.")

    result = _concat_dedup(tables)
    out = pathlib.Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    with ipc.new_file(out, result.schema) as writer:
        writer.write_table(result)
    print(f"Wrote {result.num_rows} rows → {out}", file=sys.stderr)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser(prog=None) -> tuple[argparse.ArgumentParser, ...]:
    ap = argparse.ArgumentParser(
        prog=prog,
        description="Download and manage GNSS PPP position data from EarthScope.",
    )
    sub = ap.add_subparsers(dest="command")

    # --- get ---
    get_p = sub.add_parser(
        "get",
        help="Download position data for stations from a station list.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="""Download GNSS PPP position data and store as Arrow files.

Output location:
  ./data/arrow/<GEOSNCL>/YYYYMM/<GEOSNCL>_<START>_<END>.arrow
  ./data/arrow/<GEOSNCL>/no_data.json   (days with no API data)

Downloaded data is automatically visible in the Positions tab and
Completeness & Latency tab of the web UI ('es-pos webserver').
The web UI also supports on-demand fetching via its built-in Fetch button.

Station list files are built with 'es-pos stations get' or interactively
via the Station Builder tab in the web UI.

Examples:
  es-pos fetch get -i ShakeAlert --start 2025-01-01 --end 2025-01-31
  es-pos fetch get -i ShakeAlert -i cwu --start 2025-06-01
  es-pos fetch get -i ShakeAlert --start 2025-01-01T12:00:00Z --end 2025-01-02T00:00:00Z
""",
    )
    get_p.add_argument(
        "-i",
        "--input",
        action="append",
        required=True,
        metavar="FILE",
        help=(
            "Station list JSONL file (from station_list get). May be repeated. "
            "Resolved in order: as given, with .jsonl, in data/station-lists/, "
            "in data/station-lists/ with .jsonl."
        ),
    )
    get_p.add_argument(
        "--start",
        metavar="DATETIME",
        help=(
            "Start date or datetime in ISO 8601 format "
            "(default: today UTC midnight). Example: 2025-01-01 or 2025-01-01T06:00:00Z."
        ),
    )
    get_p.add_argument(
        "--end",
        metavar="DATETIME",
        help=(
            "End date or datetime in ISO 8601 format "
            "(default: start + 1 day). Example: 2025-01-31."
        ),
    )
    get_p.add_argument(
        "--force",
        action="store_true",
        help=(
            "Ignore cached no-data markers and re-request those days from the API. "
            "Updates the marker file with the new result."
        ),
    )
    get_p.add_argument(
        "--redownload",
        action="store_true",
        help=(
            "Ignore all local caches (arrow files and no-data markers) and redownload "
            "everything. Existing files are replaced and markers are updated."
        ),
    )
    get_p.add_argument(
        "--workers",
        type=int,
        default=_DEFAULT_WORKERS,
        metavar="N",
        help=f"Number of parallel downloads (default: {_DEFAULT_WORKERS}).",
    )

    # --- concat ---
    concat_p = sub.add_parser(
        "concat",
        help="Concatenate and deduplicate multiple Arrow position files.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="""Concatenate multiple Arrow position files into one file, sorted by
time with duplicate timestamps removed.

Example:
  positions_fetch concat data/arrow/P548.CI.LY_.20/202501/*.arrow -o merged.arrow
""",
    )
    concat_p.add_argument(
        "files",
        nargs="+",
        metavar="FILE",
        help="Input Arrow files to concatenate.",
    )
    concat_p.add_argument(
        "-o",
        "--output",
        required=True,
        metavar="FILE",
        help="Output Arrow file path.",
    )

    return ap, get_p, concat_p


def main() -> None:
    ap, get_p, concat_p = _build_parser()
    args = ap.parse_args()
    if not args.command:
        ap.print_help()
        sys.exit(0)
    if args.command == "get":
        _cmd_get(args)
    elif args.command == "concat":
        _cmd_concat(args)


if __name__ == "__main__":
    main()

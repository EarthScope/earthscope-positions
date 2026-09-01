"""
positions_fetch — download GNSS PPP position data from the EarthScope API.

Uses the earthscope-sdk's async client (AsyncEarthScopeClient) for both HTTP
and credentials — token refresh, retry-on-5xx/429, and rate limiting are all
handled by the SDK internally; this module owns only the GNSS-specific
bookkeeping (which (stream, day) pairs are missing, no_data.jsonl markers,
per-station cross-process file locks, and progress reporting).

CLI (see _build_parser for the full flag list):
    --list NAME_OR_PATH [...]   Download position data (default mode)
    --retry [--result PATTERN]  Retry previously failed (error-NNN) requests

('concat' — _cmd_concat/_concat_dedup — is kept in this module but not
CLI-exposed; see _build_parser's docstring.)
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import io
import os
import pathlib
import random
import subprocess
import sys
import time
import threading
from typing import Optional

import httpx
import orjson
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.ipc as ipc
from earthscope_sdk import AsyncEarthScopeClient
from earthscope_sdk.auth.error import UnauthenticatedError, UnauthorizedError
from earthscope_sdk.config.error import ProfileDoesNotExistError
from earthscope_sdk.config.models import Tokens
from earthscope_sdk.config.settings import SdkSettings

from earthscope_positions import environment, paths

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_REFRESH_MARGIN = 60  # seconds before expiry to trigger refresh

_LOCK_TTL = 120  # lock expiry in seconds (2 minutes)

_NO_DATA_FILE = "no_data.jsonl"
_NO_DATA_FILE_LEGACY = "no_data.json"
_LOCK_FILE = ".lock"
_TS_FMT = "%Y%m%dT%H%M%SZ"  # compact UTC timestamp for filenames
_ERROR_LOG_NAME = "positions_errors.jsonl"  # under the base data directory
_MAX_RETRIES = 2  # tasks are re-queued up to this many times on transient errors
_RETRY_BASE_DELAY = 2.0  # seconds; exponential backoff base before each retry
_DEFAULT_WORKERS = 20

_UTC = dt.timezone.utc


def _project_root() -> pathlib.Path:
    return paths.project_root()


def _data_root() -> pathlib.Path:
    return paths.arrow_dir()


# ---------------------------------------------------------------------------
# SDK client
# ---------------------------------------------------------------------------


def sdk_settings() -> SdkSettings:
    """SDK settings pinned to the active environment (see
    :mod:`earthscope_positions.environment`).

    Both halves matter and have to move together: ``profile_name`` picks which
    token cache is read, ``resources.api_url`` picks which deployment is
    called.  Setting only one of them authenticates against prod and queries
    stage (or the reverse), which fails as a 401 that looks like a login
    problem rather than a configuration one.

    Anything else about the profile — the OAuth domain and audience a stage
    login needs — comes from the profile's own entry in
    ``~/.earthscope/config.toml``, which is where the ``es`` CLI already keeps
    it; duplicating it here would give it two sources of truth.
    """
    env = environment.current()
    try:
        return SdkSettings(
            profile_name=environment.profile(),
            resources={"api_url": env.api_url},
        )
    except ProfileDoesNotExistError:
        # The SDK's own message is just "Profile 'x' does not exist" — it does
        # not say where profiles live or that this install may already have a
        # working one under another name, which is the actual next step.
        sys.exit(environment.profile_setup_hint())


def _make_client() -> AsyncEarthScopeClient:
    """Create a new EarthScope SDK async client for the active environment.

    The SDK handles credentials end to end — reading the local token cache,
    refreshing before expiry, and retrying transient (429/5xx) failures — so
    there's no per-task token file/subprocess-refresh bookkeeping in this
    module anymore (see _fetch_one_day).  A thin function (rather than calling
    the constructor directly at each call site) so tests can substitute a
    fake client via monkeypatch.
    """
    return AsyncEarthScopeClient(settings=sdk_settings())


def _tokens_path() -> pathlib.Path:
    """Token cache for the active environment's profile.

    Resolved per call rather than at import: the profile follows the data
    directory now, and a module-level constant would freeze whichever one
    happened to be active when this module was first imported.
    """
    return pathlib.Path.home() / ".earthscope" / environment.profile() / "tokens.json"


def _read_tokens() -> Tokens:
    try:
        raw = _tokens_path().read_bytes()
    except FileNotFoundError:
        sys.exit(
            f"No credentials found for the {environment.label()} environment "
            f"(profile '{environment.profile()}').\n"
            f"Please authenticate: {login_command()}"
        )
    return Tokens.model_validate_json(raw)


def login_command() -> str:
    """The exact ``es user login`` invocation for the active environment.

    Every "you are not logged in" message routes through this rather than
    hard-coding ``es user login``: told the bare command while a stage
    directory is active, you log into prod and get the same error again.
    """
    prof = environment.profile()
    return "es user login" if prof == "default" else f"es user login --profile {prof}"


def _ensure_token() -> str:
    """Return a valid access token, refreshing it first if it's near expiry.

    Only used by station_list.py's radial search now — that endpoint has no
    SDK method, so it still makes a bare `requests` call and needs a bearer
    token of its own (the position-fetch path above gets this from
    AsyncEarthScopeClient instead).
    """
    tokens = _read_tokens()
    try:
        body = tokens.access_token_body
    except ValueError:
        body = None
    if body is not None and body.ttl.total_seconds() > _REFRESH_MARGIN:
        return tokens.access_token.get_secret_value()
    # ES_PROFILE rather than a --profile flag: it is the alias SdkSettings
    # validates `profile_name` from, so it steers the CLI's own settings chain
    # the same way it steers ours, and does not depend on which subcommands
    # happen to expose the flag.
    result = subprocess.run(
        ["es", "user", "refresh-access-token"],
        capture_output=True,
        text=True,
        env={**os.environ, environment.PROFILE_ENV_VAR: environment.profile()},
    )
    if result.returncode != 0:
        sys.exit(
            f"Token refresh failed for the {environment.label()} environment "
            f"(profile '{environment.profile()}'):\n"
            f"  {result.stderr.strip()}\n"
            f"  Log in with: {login_command()}"
        )
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
    """Return set of date strings (YYYY-MM-DD) where the API confirmed no data.

    Only dates with result "no-data" block future retries.  Dates recorded as
    "error-NNN" are excluded so they are re-attempted automatically — a request
    error (e.g. a bad date format that has since been fixed) should not
    permanently suppress a date.
    """
    dates: set[str] = set()
    jsonl = geosncl_dir / _NO_DATA_FILE
    if jsonl.exists():
        for line in jsonl.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = orjson.loads(line)
                d = rec.get("date")
                result = rec.get("result", "no-data")
                if d and not result.startswith("error-"):
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


def _add_no_data(
    geosncl_dir: pathlib.Path, date_str: str, result: str = "no-data"
) -> None:
    """Append one attempt record to no_data.jsonl."""
    geosncl_dir.mkdir(parents=True, exist_ok=True)
    record = (
        orjson.dumps(
            {
                "date": date_str,
                "attempted_at": dt.datetime.now(dt.timezone.utc).strftime(
                    "%Y-%m-%dT%H:%M:%SZ"
                ),
                "result": result,
            }
        ).decode()
        + "\n"
    )
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
                old.write_bytes(
                    orjson.dumps({"dates": sorted(dates)}, option=orjson.OPT_INDENT_2)
                )
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


def _log_error(geosncl: str, date_str: str, resp: httpx.Response) -> None:
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
    log_path = paths.base_dir() / _ERROR_LOG_NAME
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with _error_log_lock:
        with log_path.open("ab") as f:
            f.write(orjson.dumps(entry) + b"\n")


# ---------------------------------------------------------------------------
# Single-day fetch
# ---------------------------------------------------------------------------


async def _fetch_one_day(
    client: AsyncEarthScopeClient,
    edid: str,
    geosncl: str,
    day_start: dt.datetime,
    day_end: dt.datetime,
    force: bool,
    redownload: bool,
) -> str:
    """
    Fetch one UTC-day segment of position data via the EarthScope SDK
    (AsyncEarthScopeClient.data._get_gnss_instantaneous_positions) — the SDK
    owns auth/token refresh and retries transient (429/5xx) failures itself,
    so this function only classifies the outcome and does the same on-disk
    bookkeeping as before (Arrow file placement, no_data.jsonl markers).

    Returns:
        'ok'             — data downloaded and written
        'skipped'        — arrow file already exists (cache hit)
        'no-data-cached' — day is in no_data.json (skipped without API call)
        'no-data'        — API returned no rows or a genuine 404; no_data.json updated
        'rejected-NNN'   — API rejected the request (400/422, e.g. a malformed
                            stream_id); permanent, not retried, but distinct
                            from 'no-data' so it stays visible instead of
                            reading as an absence of data
        'error-NNN'      — other HTTP error code NNN (transient — retried, see
                            _run_parallel)
    """
    gdir = _geosncl_dir(geosncl)
    date_str = day_start.strftime("%Y-%m-%d")
    out_path = _arrow_path(gdir, day_start, day_end)

    # --- cache checks ---
    if not redownload and out_path.exists():
        return "skipped"
    if not force and not redownload and date_str in _load_no_data(gdir):
        return "no-data-cached"

    # --- acquire lock, call the API once, release lock immediately ---
    # (_acquire_lock/_release_lock are blocking file I/O — run off the event
    # loop so one slow lock-wait can't stall every other in-flight fetch.)
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _acquire_lock, gdir)
    try:
        table = await client.data._get_gnss_instantaneous_positions(
            stream_edid=edid,
            start_datetime=day_start,
            end_datetime=day_end,
        )
    except (UnauthenticatedError, UnauthorizedError) as exc:
        # Refresh itself failed (e.g. refresh token expired) — every other
        # request this run would fail identically, so stop the whole process
        # with a clear, actionable message rather than burning through it.
        sys.exit(
            f"Authentication failed against {environment.label()} ({exc}). "
            f"Please run: {login_command()}"
        )
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        if status == 404:
            # Not found — definitively no data, record permanently.
            if redownload and out_path.exists():
                out_path.unlink()
            _add_no_data(gdir, date_str, "no-data")
            return "no-data"
        if status in (400, 422):
            # API rejected the request (e.g. a stream list missing edid sends
            # the geosncl as stream_id, which the API expects as a ULID and
            # 422s on). Permanent client error — record so it stops retrying
            # (retrying an identically-malformed request would just repeat
            # the same 422 forever), but returning "no-data" here would hide
            # that distinction: the marker file would correctly say
            # "error-{status}", while every live view of this run (the
            # progress tally, the per-line log) would show a plain
            # "no-data" indistinguishable from streams that genuinely have
            # none — exactly what made this class of bug so hard to notice.
            if redownload and out_path.exists():
                out_path.unlink()
            _add_no_data(gdir, date_str, f"error-{status}")
            _log_error(geosncl, date_str, exc.response)
            return f"rejected-{status}"
        # Transient errors (5xx, 429, …) the SDK's own internal retries didn't
        # resolve — do NOT record in no_data.json; leave the day eligible for
        # this module's own outer retry (see _run_parallel). Log for inspection.
        _log_error(geosncl, date_str, exc.response)
        return f"error-{status}"
    finally:
        await loop.run_in_executor(None, _release_lock, gdir)

    if table.num_rows == 0:
        # Successful response, zero rows.
        if redownload and out_path.exists():
            out_path.unlink()
        _add_no_data(gdir, date_str, "no-data")
        return "no-data"

    # The SDK appends an "edid" column (load_table_with_extra) — drop it so
    # the on-disk schema matches every other Arrow file the rest of this app
    # (and its own _concat_dedup) expects.
    if "edid" in table.schema.names:
        table = table.drop(["edid"])

    if redownload and out_path.exists():
        out_path.unlink()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with ipc.new_stream(out_path, table.schema) as writer:
        writer.write_table(table)
    if redownload:
        _remove_no_data(gdir, date_str)
    return "ok"


# ---------------------------------------------------------------------------
# Progress display
# ---------------------------------------------------------------------------


class _Progress:
    """Thread-safe in-place progress line printed to stderr."""

    def __init__(self, total: int, precached: int = 0) -> None:
        # *precached* is (stream, day) pairs a caller already determined were
        # cached and therefore never handed to us -- the web UI filters those
        # out before spawning this process.  Counting them here keeps the
        # denominator the real total and stops a mostly-cached run from looking
        # like a full re-download of a handful of streams.
        self.total = total + precached
        self.ok = 0  # freshly downloaded
        self.cached = precached  # skipped — arrow file already present
        self.no_data = 0  # API returned nothing (new or previously known)
        self.failed = 0  # HTTP / parse error (incl. rejected-NNN: a malformed request, not an absence of data)
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
                tag = "downloaded"
            elif status == "skipped":
                self.cached += 1
                tag = "cached"
            elif status in ("no-data", "no-data-cached"):
                self.no_data += 1
                tag = "no-data"
            else:
                self.failed += 1
                tag = status  # e.g. "error-503" (transient) or "rejected-422" (permanent, bad request)
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
            f"  downloaded:{self.ok:>5}"
            f"  cached:{self.cached:>5}"
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

    def log(self, message: str) -> None:
        """Print *message* as its own line — for discrete events (a transient
        HTTP error, a retry) that must stay visible rather than being folded
        into (and instantly overwritten by) the running tally.

        In a TTY, the in-place progress line has no trailing newline, so the
        cursor sits mid-line; a leading newline moves off it first. Piped
        output (the webserver's subprocess case) already prints one full line
        per update, so no prefix is needed there.
        """
        with self._lock:
            prefix = "\n" if self._is_tty else ""
            print(f"{prefix}{message}", file=sys.stderr, flush=True)

    def finish(self) -> None:
        with self._lock:
            self._render()
            if self._is_tty:
                print(file=sys.stderr)  # move past the \r line

    def summary(self) -> str:
        elapsed_m = (time.monotonic() - self._start) / 60.0
        return (
            f"{self.ok} downloaded, {self.cached} cached (already had data), "
            f"{self.no_data} no-data, {self.failed} failed  "
            f"({elapsed_m:.1f} min)"
        )


# ---------------------------------------------------------------------------
# Parallel execution
# ---------------------------------------------------------------------------


async def _run_parallel(
    all_tasks: list[tuple],
    n_workers: int,
    progress: _Progress,
    client: AsyncEarthScopeClient,
) -> None:
    """
    Run tasks concurrently (bounded by n_workers) while ensuring at most one
    active download per station at a time.

    Tasks are grouped by station; each station's day-tasks run strictly
    sequentially (a plain loop — no cross-task coordination needed within one
    process), while different stations run concurrently under a shared
    semaphore.  The on-disk lock in _fetch_one_day still guards against a
    *separate* process touching the same station at the same time.
    """
    if not all_tasks:
        return

    by_station: dict[str, list[tuple]] = {}
    for task in all_tasks:
        _edid, geosncl, *_rest = task
        by_station.setdefault(_geosncl_label(geosncl), []).append(task)

    sem = asyncio.Semaphore(n_workers)

    async def run_one(task: tuple) -> None:
        edid, geosncl, ds, de, force, redownload, retries_left = task
        label = _geosncl_label(geosncl)

        status = "error-exception"
        try:
            async with sem:
                status = await _fetch_one_day(
                    client, edid, geosncl, ds, de, force, redownload
                )
        except Exception as exc:
            print(f"  ERROR  {label}  {ds.date()}  ({exc})", file=sys.stderr)

        # Re-try transient failures the SDK's own internal retries didn't
        # resolve. (400/422/404 are already remapped to "no-data" inside
        # _fetch_one_day, so only genuine transient errors land here.) Back
        # off first — a batch's worth of tasks retrying a busy gateway
        # instantly is exactly how one 504 burst turns into another.
        #
        # Log the status (response code included) here, immediately, whether
        # or not a retry follows — otherwise a transient error that a retry
        # later resolves never shows up anywhere in the live log, even though
        # it happened (it's still recorded in positions_errors.jsonl, but that
        # file isn't what anyone's watching in real time).
        if status.startswith("error-"):
            if retries_left > 0:
                attempt = _MAX_RETRIES - retries_left  # 0 on the first retry
                delay = _RETRY_BASE_DELAY * (2**attempt) + random.uniform(0, _RETRY_BASE_DELAY)
                progress.log(
                    f"  {status:<12} {label}  {ds.date()}  "
                    f"— retrying in {delay:.1f}s ({retries_left} attempt(s) left)"
                )
                await asyncio.sleep(delay)
                await run_one((edid, geosncl, ds, de, force, redownload, retries_left - 1))
                return
            progress.log(f"  {status:<12} {label}  {ds.date()}  — giving up after {_MAX_RETRIES} retries")

        progress.update(status, label, ds.date())

    async def run_station(tasks: list[tuple]) -> None:
        for task in tasks:
            await run_one(task)

    await asyncio.gather(*(run_station(tasks) for tasks in by_station.values()))


# ---------------------------------------------------------------------------
# Stream list loading
# ---------------------------------------------------------------------------


def _parse_jsonl_line(raw_line: bytes) -> dict | None:
    """Parse one JSONL line, stripping a grep-style 'filename:' prefix if needed."""
    line = raw_line.strip()
    if not line:
        return None
    try:
        return orjson.loads(line)
    except orjson.JSONDecodeError:
        # Recover from grep artifact: "path/to/file.jsonl:{...}"
        idx = line.find(b"{")
        if idx > 0:
            try:
                return orjson.loads(line[idx:])
            except orjson.JSONDecodeError:
                pass
    return None


def _load_station_list(path_str: str) -> list[dict]:
    p = pathlib.Path(path_str)
    stem = p.stem if p.suffix in (".jsonl", ".json") else p.name
    sl = paths.stream_lists_dir()
    candidates = [
        p,
        p.parent / (stem + ".jsonl"),
        sl / p.name,
        sl / (stem + ".jsonl"),
        sl / (stem + ".json"),  # backward compat
    ]
    for c in dict.fromkeys(candidates):
        if c.exists():
            raw = c.read_bytes()
            if c.suffix == ".json":
                return orjson.loads(raw)
            return [
                r
                for line in raw.splitlines()
                if (r := _parse_jsonl_line(line)) is not None
            ]
    tried = ", ".join(str(c) for c in dict.fromkeys(candidates))
    sys.exit(f"Stream list not found. Tried: {tried}")


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
    for path_str in args.list:
        for rec in _load_station_list(path_str):
            edid = rec.get("edid") or rec.get("geosncl")
            if edid and edid not in seen_edids:
                seen_edids.add(edid)
                stations.append(rec)

    if not stations:
        sys.exit("No stations found in the provided stream lists.")

    # Backfill edid for any record that only has a geosncl — the API's
    # stream_id query param needs the real EDID (a ULID); a request sent with
    # the geosncl string instead gets a 422 from the server ("ulid: bad data
    # size when unmarshaling"), which reads as "no-data" in the live progress
    # line even though it's a malformed-request error, not an absence of
    # data. Same fallback source _cmd_retry already uses.
    missing = [r for r in stations if not r.get("edid")]
    if missing:
        edid_map = _build_edid_map(paths.arrow_dir())
        backfilled = 0
        for rec in missing:
            eid = edid_map.get(rec.get("geosncl", ""))
            if eid:
                rec["edid"] = eid
                backfilled += 1
        if backfilled:
            print(f"  (backfilled edid for {backfilled}/{len(missing)} stream(s) missing it)", file=sys.stderr)
        still_missing = [r.get("geosncl", "?") for r in missing if not r.get("edid")]
        if still_missing:
            suffix = f" … and {len(still_missing) - 10} more" if len(still_missing) > 10 else ""
            print(
                f"  [warn] no edid found for {len(still_missing)} stream(s), "
                f"will be requested by geosncl and likely 422: "
                f"{', '.join(still_missing[:10])}{suffix}",
                file=sys.stderr,
            )

    day_segs = _day_ranges(start, end)
    n_tasks = len(stations) * len(day_segs)
    print(
        f"{len(stations)} station(s), {len(day_segs)} day-segment(s), "
        f"{n_tasks} task(s)",
        file=sys.stderr,
    )

    stations_sorted = sorted(
        stations, key=lambda r: r.get("geosncl") or r.get("edid", "")
    )
    all_tasks = [
        (
            rec.get("edid") or rec.get("geosncl"),
            rec.get("geosncl") or rec.get("edid", ""),
            ds,
            de,
            args.force,
            args.redownload,
            _MAX_RETRIES,
        )
        for ds, de in day_segs
        for rec in stations_sorted
    ]
    asyncio.run(_run_tasks(all_tasks, args.workers,
                           getattr(args, "precached", 0) or 0))


async def _run_tasks(all_tasks: list[tuple], workers: int, precached: int = 0) -> None:
    """Run *all_tasks* against one shared SDK client for this process's
    lifetime (one client per CLI invocation — this module is always run as
    either a direct CLI command or a fresh subprocess, never imported into a
    long-lived process), reporting progress as it goes.

    *precached* is the number of (stream, day) pairs the caller already found
    cached and excluded from *all_tasks*; they are folded into the tally so the
    displayed totals describe the whole request, not just its remainder.
    """
    progress = _Progress(len(all_tasks), precached)
    async with _make_client() as client:
        await _run_parallel(all_tasks, workers, progress, client)
    progress.finish()
    print(f"Done: {progress.summary()}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Command: retry
# ---------------------------------------------------------------------------


def _retry_result_matches(result: str, pattern: str) -> bool:
    """Return True when *result* matches *pattern*.

    Pattern rules (case-insensitive):
      "error-422"  – exact match on that one code
      "error-*"    – any error-NNN result
      "*"          – every result (including "no-data")
    """
    p = pattern.lower()
    r = result.lower()
    if p in ("*", "all"):
        return True
    if p in ("error", "error-*", "errors"):
        return r.startswith("error-")
    return r == p


def _build_edid_map(data_dir: pathlib.Path) -> dict[str, str]:
    """Scan all stream-list JSONL files and return {geosncl: edid}.

    Only records with a genuine ``edid`` field contribute — no falling back
    to the geosncl itself for either side. That fallback used to let a
    stream list saved without edid (e.g. before api_save_stream_list started
    including it) "poison" the map with a bogus self-mapped entry
    (geosncl -> geosncl); since this scans files in alphabetical order and
    uses setdefault, whichever file came first alphabetically won regardless
    of whether it actually had a real edid — silently blocking a later,
    correct file from ever filling in the right value.
    """
    mapping: dict[str, str] = {}
    sl_dir = paths.stream_lists_dir()
    search_dirs = [sl_dir, data_dir.parent / "stream-lists"]
    for directory in dict.fromkeys(search_dirs):
        if not directory.exists():
            continue
        for sl_file in sorted(directory.glob("*.jsonl")):
            try:
                for line in sl_file.read_bytes().splitlines():
                    if not line.strip():
                        continue
                    rec = orjson.loads(line)
                    gs = rec.get("geosncl", "")
                    eid = rec.get("edid", "")
                    if gs and eid:
                        mapping.setdefault(gs, eid)
            except Exception:
                pass
    return mapping


def _cmd_retry(args) -> None:
    """Retry all no_data.jsonl entries whose result matches --result."""
    data_dir = paths.arrow_dir()
    if not data_dir.exists():
        sys.exit(f"Data directory not found: {data_dir}")

    pattern = getattr(args, "result", "error-*") or "error-*"
    edid_map = _build_edid_map(data_dir)

    # Collect all matching (edid, geosncl, date) tuples; deduplicate.
    seen: set[tuple[str, str]] = set()
    candidates: list[tuple[str, str, dt.date]] = []

    for no_data_file in sorted(data_dir.rglob("no_data.jsonl")):
        geosncl = no_data_file.parent.name
        try:
            lines = no_data_file.read_text(encoding="utf-8").splitlines()
        except Exception:
            continue
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                rec = orjson.loads(line)
            except Exception:
                continue
            result = rec.get("result", "")
            date_str = rec.get("date", "")
            if not date_str or not _retry_result_matches(result, pattern):
                continue
            key = (geosncl, date_str)
            if key in seen:
                continue
            seen.add(key)
            edid = edid_map.get(geosncl, geosncl)
            try:
                candidates.append((edid, geosncl, dt.date.fromisoformat(date_str)))
            except ValueError:
                pass

    if not candidates:
        print(
            f"No entries matching result={pattern!r} found under {data_dir}",
            file=sys.stderr,
        )
        return

    candidates.sort(key=lambda t: (t[1], t[2]))

    if args.dry_run:
        print(
            f"Would retry {len(candidates)} entry/entries "
            f"(result matches {pattern!r}):",
            file=sys.stderr,
        )
        for edid, gs, day in candidates[:30]:
            print(f"  {gs}  {day}", file=sys.stderr)
        if len(candidates) > 30:
            print(f"  … and {len(candidates) - 30} more", file=sys.stderr)
        return

    print(
        f"Retrying {len(candidates)} entry/entries " f"(result matches {pattern!r}) …",
        file=sys.stderr,
    )

    all_tasks = []
    for edid, geosncl, day in candidates:
        day_start = dt.datetime(day.year, day.month, day.day, tzinfo=_UTC)
        day_end = day_start + dt.timedelta(days=1)
        all_tasks.append(
            (
                edid,
                geosncl,
                day_start,
                day_end,
                False,  # force
                True,  # redownload — removes error entry on success
                _MAX_RETRIES,
            )
        )

    asyncio.run(_run_tasks(all_tasks, args.workers))


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


def _build_parser(prog=None) -> argparse.ArgumentParser:
    """One flat command — no subcommands.  Default mode downloads --list;
    --retry switches to retrying previously failed (error-NNN) requests.

    ('concat' used to be a subcommand here; the code (_cmd_concat /
    _concat_dedup) is still in this module for later, just not wired up to
    the CLI.)
    """
    ap = argparse.ArgumentParser(
        prog=prog,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="""Download GNSS PPP position data and store as Arrow files.

Output location:
  ./data/arrow/<GEOSNCL>/YYYYMM/<GEOSNCL>_<START>_<END>.arrow
  ./data/arrow/<GEOSNCL>/no_data.json   (days with no API data)

Downloaded data is automatically visible in the Positions tab and
Completeness & Latency tab of the web UI ('es-pos webserver').
The web UI also supports on-demand fetching via its built-in Fetch button.

Stream list files are built with 'es-pos lists get-streams' or interactively
via the Stream List Builder tab in the web UI.

Examples:
  es-pos fetch --list ShakeAlert --start 2025-01-01 --end 2025-01-31
  es-pos fetch --list ShakeAlert --list cwu --start 2025-06-01
  es-pos fetch --list ShakeAlert --start 2025-01-01T12:00:00Z --end 2025-01-02T00:00:00Z

  # Retry every previously failed (error-NNN) request found anywhere in the data directory:
  es-pos fetch --retry
  es-pos fetch --retry --result error-422
  es-pos fetch --retry --dry-run
""",
    )
    ap.add_argument(
        "--list",
        action="append",
        metavar="NAME_OR_PATH",
        help=(
            "Stream list to fetch — either a bare name (resolved against "
            "data/stream-lists/) or a path to a JSONL file. May be repeated. "
            "Required unless --retry is given."
        ),
    )
    ap.add_argument(
        "--start",
        metavar="DATETIME",
        help=(
            "Start date or datetime in ISO 8601 format "
            "(default: today UTC midnight). Example: 2025-01-01 or 2025-01-01T06:00:00Z."
        ),
    )
    ap.add_argument(
        "--end",
        metavar="DATETIME",
        help=(
            "End date or datetime in ISO 8601 format "
            "(default: start + 1 day). Example: 2025-01-31."
        ),
    )
    ap.add_argument(
        "--force",
        action="store_true",
        help=(
            "Ignore cached no-data markers and re-request those days from the API. "
            "Updates the marker file with the new result."
        ),
    )
    ap.add_argument(
        "--redownload",
        action="store_true",
        help=(
            "Ignore all local caches (arrow files and no-data markers) and redownload "
            "everything. Existing files are replaced and markers are updated."
        ),
    )
    ap.add_argument(
        "--workers",
        type=int,
        default=_DEFAULT_WORKERS,
        metavar="N",
        help=f"Number of parallel downloads (default: {_DEFAULT_WORKERS}).",
    )
    ap.add_argument(
        "--precached",
        type=int,
        default=0,
        metavar="N",
        help=(
            "Number of (stream, day) pairs the caller already determined were "
            "cached and excluded from --list.  Folded into the progress totals so "
            "they describe the whole request rather than only its remainder.  Set "
            "by the web UI, which filters cache hits before invoking this."
        ),
    )
    ap.add_argument(
        "--retry",
        action="store_true",
        help=(
            "Retry mode: scan every no_data.jsonl file under the data directory and "
            "retry any entry whose result matches --result, instead of fetching --list. "
            "Ignores --list/--start/--end/--force/--redownload."
        ),
    )
    ap.add_argument(
        "--result",
        metavar="PATTERN",
        default="error-*",
        help="(--retry only) Result pattern to retry: 'error-*' (all errors, default), 'error-422', etc.",
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="(--retry only) Print matching entries without downloading.",
    )
    return ap


def main() -> None:
    ap = _build_parser()
    args = ap.parse_args()
    if args.retry:
        _cmd_retry(args)
    elif args.list:
        _cmd_get(args)
    else:
        ap.error("--list is required unless --retry is given")


if __name__ == "__main__":
    main()

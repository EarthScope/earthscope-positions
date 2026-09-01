"""
positions_diagnose — systematic concurrency sweep of the EarthScope positions API.

Iterates from --min-workers to --max-workers, testing each endpoint in series
(auth first, then open) at each concurrency level. Every request result is
saved as a JSON line to a JSONL file for post-run analysis.

Endpoints tested (both follow the active environment — see
``earthscope_positions.environment``; the hosts below are production's):
  auth: api.earthscope.org/beta/data-products/gnss/positions/instantaneous
  open: gnss-observations-api.prod.earthscope.org/positions/instantaneous/v2

Stage has no known unauthenticated equivalent, so a stage run sweeps the
authenticated endpoint alone rather than probing a guessed hostname.

Per-request output fields:
  endpoint, worker_count, geosncl, edid, date, status, latency_ms,
  row_count (rows in the Arrow table, or null), result, body (error detail),
  ts_utc

Designed for overnight runs (6-8 hours) with --total-duration.

Usage:
    positions_diagnose -i ShakeAlert.clean --start 2026-01-01
    positions_diagnose -i ShakeAlert.clean --total-duration 25200  # 7 h
    positions_diagnose -i ShakeAlert.clean --min-workers 1 --max-workers 10 --total-duration 3600
"""
from __future__ import annotations

import argparse
import datetime as dt
import io
import itertools
import math
import pathlib
import sys
import threading
import time
from typing import Optional

import orjson
import pyarrow.ipc
import requests

from earthscope_positions import environment, paths
from earthscope_positions.fetch.positions_fetch import (
    _ensure_token,
    _load_station_list,
    _parse_datetime,
    _project_root,
    _UTC,
)

# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

_AUTH_PATH = "/beta/data-products/gnss/positions/instantaneous/v2"


def _endpoint_auth() -> str:
    """Authenticated positions endpoint for the active environment."""
    return environment.api_url().rstrip("/") + _AUTH_PATH


def _endpoint_open() -> "str | None":
    """Unauthenticated positions endpoint, or None where the environment has
    none.  Only production publishes one; see environment.Environment."""
    return environment.current().open_positions_url

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_REQUEST_TIMEOUT = 30        # shorter than fetch since we're probing
_DEFAULT_TOTAL_DURATION = 25200  # 7 hours
_DEFAULT_MAX_WORKERS = 40
_DEFAULT_SAMPLE = 200


def _logspace_workers(max_w: int, n_steps: int = 12) -> list[int]:
    """Return worker counts in log space from 1 to max_w, always including both endpoints."""
    if max_w <= 1:
        return [1]
    log_max = math.log10(max_w)
    raw = [10 ** (i * log_max / (n_steps - 1)) for i in range(n_steps)]
    counts = sorted({max(1, min(max_w, round(v))) for v in raw})
    return counts

# ---------------------------------------------------------------------------
# Single probe — returns a dict that maps directly to one JSONL line
# ---------------------------------------------------------------------------


def _probe(
    endpoint_label: str,
    endpoint_url: str,
    edid: str,
    geosncl: str,
    day_start: dt.datetime,
    day_end: dt.datetime,
    token: Optional[str],
    worker_count: int,
) -> dict:
    headers: dict[str, str] = {
        "accept": "application/vnd.apache.arrow.stream",
        "accept-encoding": "",
    }
    if token:
        headers["authorization"] = f"Bearer {token}"

    date_str = day_start.strftime("%Y-%m-%d")
    ts_utc = dt.datetime.now(_UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    t0 = time.monotonic()
    try:
        resp = requests.get(
            endpoint_url,
            params={
                "stream_id": edid,
                "start_datetime": day_start.isoformat(),
                "end_datetime": day_end.isoformat(),
            },
            headers=headers,
            timeout=_REQUEST_TIMEOUT,
        )
    except requests.RequestException as exc:
        return {
            "endpoint": endpoint_label,
            "worker_count": worker_count,
            "geosncl": geosncl,
            "edid": edid,
            "date": date_str,
            "status": 0,
            "latency_ms": round((time.monotonic() - t0) * 1000, 1),
            "row_count": None,
            "result": "exception",
            "body": str(exc)[:300],
            "ts_utc": ts_utc,
        }

    latency_ms = round((time.monotonic() - t0) * 1000, 1)
    row_count = None
    body = None
    result = "unknown"

    if resp.status_code == 200:
        buf = io.BytesIO(resp.content)
        try:
            table = pyarrow.ipc.open_file(buf).read_all()
        except Exception:
            buf.seek(0)
            try:
                # gnss-observations-api returns IPC stream format, not file format
                table = pyarrow.ipc.open_stream(buf).read_all()
            except Exception:
                table = None
        row_count = len(table) if table is not None else 0
        result = "ok" if row_count > 0 else "no-data"
    elif resp.status_code == 404:
        result = "no-data"
    else:
        result = f"error-{resp.status_code}"
        try:
            body = resp.json()
        except Exception:
            body = resp.text[:400] if resp.text else None

    return {
        "endpoint": endpoint_label,
        "worker_count": worker_count,
        "geosncl": geosncl,
        "edid": edid,
        "date": date_str,
        "status": resp.status_code,
        "latency_ms": latency_ms,
        "row_count": row_count,
        "result": result,
        "body": body,
        "ts_utc": ts_utc,
    }


# ---------------------------------------------------------------------------
# Per-phase metrics (lightweight, just for the live progress line)
# ---------------------------------------------------------------------------


class _PhaseMetrics:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.counts: dict[int, int] = {}
        self.latencies: list[float] = []
        self.total = 0
        self._start = time.monotonic()

    def record(self, status: int, latency_ms: float) -> None:
        with self._lock:
            self.counts[status] = self.counts.get(status, 0) + 1
            self.latencies.append(latency_ms)
            self.total += 1

    def elapsed_s(self) -> float:
        return time.monotonic() - self._start

    def rps(self) -> float:
        e = self.elapsed_s()
        return self.total / e if e > 0 else 0.0

    def avg_ms(self) -> float:
        with self._lock:
            return sum(self.latencies) / len(self.latencies) if self.latencies else 0.0


# ---------------------------------------------------------------------------
# Phase runner
# ---------------------------------------------------------------------------


def _run_phase(
    endpoint_label: str,
    endpoint_url: str,
    token: Optional[str],
    worker_count: int,
    tasks: list[tuple],
    phase_duration_s: float,
    phase_index: int,
    total_phases: int,
    out_lock: threading.Lock,
    out_file,
) -> _PhaseMetrics:
    """
    Run one phase: `worker_count` concurrent workers against `endpoint_label`
    for `phase_duration_s` seconds, writing every result to `out_file`.
    Workers stop cleanly after the phase duration, even if mid-request.
    """
    task_cycle = itertools.cycle(tasks)
    task_lock = threading.Lock()

    def next_task() -> tuple:
        with task_lock:
            return next(task_cycle)

    metrics = _PhaseMetrics()
    done = threading.Event()

    def worker() -> None:
        while not done.is_set():
            edid, geosncl, day_start, day_end = next_task()
            rec = _probe(
                endpoint_label, endpoint_url, edid, geosncl,
                day_start, day_end, token, worker_count,
            )
            # Record even if done was set during the request — the worker_count
            # label is still accurate and the data is valid.
            metrics.record(rec["status"], rec["latency_ms"])
            line = orjson.dumps(rec, option=orjson.OPT_NON_STR_KEYS) + b"\n"
            with out_lock:
                out_file.write(line)
                out_file.flush()

    threads = [
        threading.Thread(target=worker, daemon=True, name=f"diag-{i}")
        for i in range(worker_count)
    ]
    for t in threads:
        t.start()

    phase_start = time.monotonic()
    ep_tag = endpoint_label

    while True:
        elapsed = time.monotonic() - phase_start
        if elapsed >= phase_duration_s:
            break

        total_elapsed_m = (phase_index * phase_duration_s + elapsed) / 60
        codes = sorted(metrics.counts.items())
        code_str = "  ".join(f"{c}:{n}" for c, n in codes) or "—"

        line = (
            f"  [{ep_tag:4s}  w:{worker_count:>2d}  phase {phase_index+1}/{total_phases}]"
            f"  {elapsed/60:.1f}/{phase_duration_s/60:.1f}m"
            f"  overall:{total_elapsed_m:.0f}m"
            f"  {metrics.rps():.1f}req/s"
            f"  {code_str}"
            f"  avg:{metrics.avg_ms():.0f}ms"
        )

        if sys.stderr.isatty():
            print(f"\r{line:<160}", end="", file=sys.stderr, flush=True)
        else:
            print(line, file=sys.stderr, flush=True)

        time.sleep(1.0)

    done.set()
    for t in threads:
        t.join(timeout=_REQUEST_TIMEOUT + 2)

    if sys.stderr.isatty():
        print(file=sys.stderr)

    return metrics


# ---------------------------------------------------------------------------
# Phase summary (printed after each phase completes)
# ---------------------------------------------------------------------------


def _print_phase_summary(
    endpoint_label: str,
    worker_count: int,
    metrics: _PhaseMetrics,
    phase_duration_s: float,
) -> None:
    total = metrics.total
    codes = sorted(metrics.counts.items())

    def pct(n: int) -> str:
        return f"{100*n/total:.0f}%" if total else "0%"

    code_str = "  ".join(f"{c}:{n}({pct(n)})" for c, n in codes)
    print(
        f"    [{endpoint_label:4s}  w:{worker_count:>2d}]"
        f"  {total} req  {metrics.rps():.1f}req/s"
        f"  avg:{metrics.avg_ms():.0f}ms"
        f"  {code_str}",
        file=sys.stderr,
    )


# ---------------------------------------------------------------------------
# Top-level run
# ---------------------------------------------------------------------------


def _run(
    stations: list[dict],
    start: dt.datetime,
    end: dt.datetime,
    max_workers: int,
    total_duration_s: float,
    output_path: pathlib.Path,
    token: str,
) -> None:
    worker_counts = _logspace_workers(max_workers)
    endpoint_auth = _endpoint_auth()
    endpoint_open = _endpoint_open()
    # Each worker count tests auth then open — in series.  An environment with
    # no open endpoint (stage) contributes only the auth phase, so the phase
    # budget divides by however many endpoints actually exist rather than
    # always by two.
    endpoints: list[tuple[str, str, "str | None"]] = [("auth", endpoint_auth, token)]
    if endpoint_open:
        endpoints.append(("open", endpoint_open, None))
    else:
        print(
            f"[note] {environment.label()} has no unauthenticated positions "
            f"endpoint; sweeping the authenticated one only.",
            file=sys.stderr,
        )
    phase_configs = [
        (w, ep_label, ep_url, tok)
        for w in worker_counts
        for ep_label, ep_url, tok in endpoints
    ]

    n_phases = len(phase_configs)
    phase_duration_s = total_duration_s / n_phases

    # Build task list ordered by start date, then geosncl
    stations_sorted = sorted(stations, key=lambda r: r.get("geosncl") or r.get("edid", ""))
    day_tasks: list[tuple] = []
    cursor = start
    while cursor < end:
        day_end = min(cursor + dt.timedelta(days=1), end)
        for rec in stations_sorted:
            day_tasks.append((
                rec["edid"],
                rec.get("geosncl") or rec["edid"],
                cursor,
                day_end,
            ))
        cursor = day_end

    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Write a metadata header line so the file is self-describing
    meta = {
        "_meta": True,
        "run_ts": dt.datetime.now(_UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "stations": len(stations),
        "date_range": f"{start.date()}/{end.date()}",
        "task_combinations": len(day_tasks),
        "worker_counts": worker_counts,
        "max_workers": max_workers,
        "n_phases": n_phases,
        "phase_duration_s": round(phase_duration_s, 1),
        "total_duration_s": total_duration_s,
        "environment": environment.name(),
        "endpoint_auth": endpoint_auth,
        "endpoint_open": endpoint_open,
    }

    print(f"\nOutput → {output_path}", file=sys.stderr)
    print(
        f"Sweep: {worker_counts} × {len(endpoints)} endpoint(s) = {n_phases} phases "
        f"({environment.label()})",
        file=sys.stderr,
    )
    print(
        f"Phase duration: {phase_duration_s/60:.1f} min  |  "
        f"Total: {total_duration_s/3600:.1f} h",
        file=sys.stderr,
    )
    print(
        f"Task pool: {len(day_tasks)} (station×day), cycling",
        file=sys.stderr,
    )
    print("", file=sys.stderr)

    out_lock = threading.Lock()

    with output_path.open("ab") as out_file:
        out_file.write(orjson.dumps(meta) + b"\n")
        out_file.flush()

        for phase_index, (worker_count, ep_label, ep_url, tok) in enumerate(phase_configs):
            print(
                f"[Phase {phase_index+1}/{n_phases}]"
                f"  endpoint={ep_label}  workers={worker_count}  "
                f"duration={phase_duration_s/60:.1f}min",
                file=sys.stderr,
            )
            metrics = _run_phase(
                endpoint_label=ep_label,
                endpoint_url=ep_url,
                token=tok,
                worker_count=worker_count,
                tasks=day_tasks,
                phase_duration_s=phase_duration_s,
                phase_index=phase_index,
                total_phases=n_phases,
                out_lock=out_lock,
                out_file=out_file,
            )
            _print_phase_summary(ep_label, worker_count, metrics, phase_duration_s)

    print(f"\nDone. Results → {output_path}", file=sys.stderr)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser(prog=None) -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog=prog,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="""Systematic concurrency sweep of the EarthScope positions API.

Worker counts are spaced logarithmically from 1 to --max-workers (~12 levels),
testing each endpoint in series (auth then open) at each level.
Every request is saved to a JSONL file for post-run analysis.

Both endpoints follow the active data directory's environment.  On stage
(api.dev.earthscope.org) there is no unauthenticated endpoint, so only the
auth phase runs.

NOTE: The auth endpoint (api.earthscope.org) requires the EarthScope VPN.
      The open endpoint (gnss-observations-api.prod.earthscope.org) is always
      reachable, but results for auth will be errors without VPN access.

Fields per record:
  endpoint, worker_count, geosncl, edid, date, status, latency_ms,
  row_count (Arrow rows, null if no data/error), result, body, ts_utc

result values:
  ok           200 with data rows
  no-data      200 with 0 rows or 404
  error-N      HTTP status N (e.g. error-500)
  exception    network/timeout error

Examples:
  es-pos test fetch -i ShakeAlert.clean --start 2026-01-01
  es-pos test fetch -i ShakeAlert.clean --total-duration 25200   # 7 h
  es-pos test fetch -i ShakeAlert.clean --max-workers 20 --total-duration 7200
""",
    )
    ap.add_argument(
        "-i", "--input",
        action="append",
        required=True,
        metavar="FILE",
        help="Station list file (repeatable).",
    )
    ap.add_argument(
        "--start",
        metavar="DATE",
        help="Start date for the test date range (default: 30 days ago).",
    )
    ap.add_argument(
        "--end",
        metavar="DATE",
        help="End date for the test date range (default: start + 30 days).",
    )
    ap.add_argument(
        "--total-duration",
        type=int,
        default=_DEFAULT_TOTAL_DURATION,
        metavar="SEC",
        help=f"Total run time in seconds (default: {_DEFAULT_TOTAL_DURATION} = 7 h).",
    )
    ap.add_argument(
        "--max-workers",
        type=int,
        default=_DEFAULT_MAX_WORKERS,
        metavar="N",
        help=f"Maximum worker count (default: {_DEFAULT_MAX_WORKERS}). "
             "Worker counts are spaced logarithmically from 1 to this value.",
    )
    ap.add_argument(
        "--sample",
        type=int,
        default=_DEFAULT_SAMPLE,
        metavar="N",
        help=f"Max stations to sample from the list (default: {_DEFAULT_SAMPLE}).",
    )
    ap.add_argument(
        "--output",
        metavar="FILE",
        help="Output JSONL path (default: data/positions_diagnose/diagnose_TIMESTAMP.jsonl).",
    )
    return ap


def _dispatch(args: argparse.Namespace) -> None:
    # Load and deduplicate stations
    stations: list[dict] = []
    seen: set[str] = set()
    for path_str in args.input:
        for rec in _load_station_list(path_str):
            edid = rec.get("edid")
            if edid and edid not in seen:
                seen.add(edid)
                stations.append(rec)

    if not stations:
        sys.exit("No stations found in the provided station list(s).")

    if len(stations) > args.sample:
        import random as _random
        sampled = _random.sample(stations, args.sample)
        stations = sorted(sampled, key=lambda r: r.get("geosncl") or r.get("edid", ""))
        print(f"Sampled {len(stations)} of {len(seen)} stations.", file=sys.stderr)
    else:
        print(f"Using all {len(stations)} station(s).", file=sys.stderr)

    # Date range
    if args.start:
        start = _parse_datetime(args.start)
    else:
        start = (dt.datetime.now(_UTC) - dt.timedelta(days=30)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
    end = _parse_datetime(args.end) if args.end else start + dt.timedelta(days=30)
    if end <= start:
        sys.exit("--end must be after --start")

    if args.max_workers < 1:
        sys.exit("--max-workers must be >= 1")

    # Output path
    if args.output:
        output_path = pathlib.Path(args.output)
        if output_path.parent == pathlib.Path("."):
            output_path = paths.positions_diagnose_dir() / output_path.name
    else:
        ts = dt.datetime.now(_UTC).strftime("%Y%m%dT%H%M%SZ")
        output_path = paths.positions_diagnose_dir() / f"diagnose_{ts}.jsonl"

    worker_counts = _logspace_workers(args.max_workers)
    n_phases = len(worker_counts) * 2
    phase_min = args.total_duration / n_phases / 60
    print(
        f"Range: {start.date()} → {end.date()}  |  "
        f"workers: {worker_counts}  |  "
        f"{n_phases} phases × {phase_min:.1f} min",
        file=sys.stderr,
    )

    token = _ensure_token()
    _run(
        stations=stations,
        start=start,
        end=end,
        max_workers=args.max_workers,
        total_duration_s=args.total_duration,
        output_path=output_path,
        token=token,
    )


def main() -> None:
    ap = _build_parser()
    args = ap.parse_args()
    _dispatch(args)


if __name__ == "__main__":
    main()

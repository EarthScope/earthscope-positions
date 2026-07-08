"""
Kafka replay of compact GeoJSON GNSS position data.

Reads Arrow position files and writes compact NDJSON records to a Kafka
topic, timed so each message is sent at the wall-clock time corresponding
to its original ingest arrival:

    send_at = start_replay_wall + (data_arrival - start_data) / time_scale

where data_arrival = data_time + ingest_latency (if apply_latency).

This module owns a singleton replay state so the webserver can expose
its status across page navigations and browser close/reopen.
"""
from __future__ import annotations

import datetime as dt
import heapq
import json
import pathlib
import sys
import threading
import time
import uuid
from typing import Any, Generator

import pyarrow.ipc as ipc

_UTC = dt.timezone.utc

# ─── Singleton state ──────────────────────────────────────────────────────────

_lock = threading.Lock()
_state: dict[str, Any] = {"status": "idle"}
_preload_thread: threading.Thread | None = None
_replay_thread: threading.Thread | None = None
_cancel = threading.Event()


def get_state() -> dict[str, Any]:
    with _lock:
        return dict(_state)


def _set(**kw: Any) -> None:
    with _lock:
        _state.update(kw)


# ─── GEOSNCL filter ───────────────────────────────────────────────────────────

def filter_geosncls(
    geosncls: list[str],
    centers: list[str],
    sol_types: list[str],
) -> list[str]:
    """Keep only geosncls matching the given center and combined sol_type lists.

    Empty list for any parameter means "accept all".
    GEOSNCL format: STATION.CENTER.LY_.ST  where ST[:2] is the combined
    2-character solution+type code (e.g. "30" = Septa Fast).
    """
    out = []
    for gs in geosncls:
        parts = gs.split(".")
        if len(parts) < 4:
            out.append(gs)
            continue
        center   = parts[1]
        loc      = parts[3]
        sol_type = loc[:2]
        if centers   and center   not in centers:   continue
        if sol_types and sol_type not in sol_types: continue
        out.append(gs)
    return out


# ─── Arrow file discovery ─────────────────────────────────────────────────────

def find_arrow_files(
    geosncls: list[str],
    start: dt.date,
    stop: dt.date,
    data_dir: pathlib.Path,
) -> tuple[list[tuple[str, pathlib.Path]], list[str]]:
    """Scan data_dir for Arrow files in [start, stop] for each geosncl.

    Returns:
        found   — list of (geosncl, path) pairs
        missing — geosncls with no files in the date range
    """
    found:   list[tuple[str, pathlib.Path]] = []
    missing: list[str] = []
    for gs in geosncls:
        gs_dir = data_dir / gs
        if not gs_dir.exists():
            missing.append(gs)
            continue
        prefix = gs + "_"
        station_files: list[pathlib.Path] = []
        for p in sorted(gs_dir.rglob("*.arrow")):
            if ".completeness" in p.name or "_ppsd" in p.name:
                continue
            stem = p.stem
            if not stem.startswith(prefix):
                continue
            rest = stem[len(prefix):]
            try:
                file_date = dt.date(int(rest[:4]), int(rest[4:6]), int(rest[6:8]))
            except (ValueError, IndexError):
                continue
            if start <= file_date <= stop:
                station_files.append(p)
        if station_files:
            for p in station_files:
                found.append((gs, p))
        else:
            missing.append(gs)
    return found, missing


# ─── Compact record generator ─────────────────────────────────────────────────

class _HeapItem:
    """Heap item — ordered by (arrival_ms, seq) so iterators are never compared."""
    __slots__ = ("arrival_ms", "seq", "key_b", "val_b", "gen_id")

    def __init__(self, arrival_ms: int, seq: int, key_b: bytes, val_b: bytes, gen_id: int):
        self.arrival_ms = arrival_ms
        self.seq        = seq
        self.key_b      = key_b
        self.val_b      = val_b
        self.gen_id     = gen_id

    def __lt__(self, other: "_HeapItem") -> bool:
        if self.arrival_ms != other.arrival_ms:
            return self.arrival_ms < other.arrival_ms
        return self.seq < other.seq


def _file_row_gen(
    path: pathlib.Path,
    geosncl: str,
    apply_latency: bool,
) -> Generator[tuple[int, bytes, bytes], None, None]:
    """Yield (arrival_ms, key_bytes, value_bytes) lazily, one batch at a time.

    Reads Arrow IPC batches on demand so the first next() call is fast — only
    the first batch is read, not the entire file.  GNSS position files are
    already time-sorted, so no cross-batch sort is needed.
    """
    try:
        reader = ipc.open_stream(path)
    except Exception:
        return

    key_b = geosncl.encode("utf-8")
    rate: int | float = 1

    for batch in reader:
        n = batch.num_rows
        if n == 0:
            continue

        def _col(name: str, default: Any = None) -> list:
            try:
                return batch.column(name).to_pylist()
            except Exception:
                return [default] * n

        times = _col("time")
        east  = _col("east")
        north = _col("north")
        up    = _col("up")
        sigEE = _col("sigEE")
        sigNN = _col("sigNN")
        sigUU = _col("sigUU")
        q_col = _col("qChannel")
        lats  = _col("ingestLatency", 0)

        # Compute sample rate from the first batch; reuse for subsequent batches.
        valid = [t for t in times if t is not None]
        if len(valid) >= 2:
            diffs = sorted(
                valid[i + 1] - valid[i]
                for i in range(min(200, len(valid) - 1))
                if valid[i + 1] != valid[i]
            )
            if diffs:
                med_ms = float(diffs[len(diffs) // 2])
                if med_ms > 0:
                    hz = 1000.0 / med_ms
                    rate = int(hz) if hz == int(hz) else hz

        for i in range(n):
            t = times[i]
            if t is None:
                continue
            lat     = lats[i] or 0
            arrival = t + lat if apply_latency else t
            rec = {
                "time": t,
                "Q":    q_col[i],
                "type": "ENU",
                "SNCL": geosncl,
                "coor": [east[i], north[i], up[i]],
                "err":  [sigEE[i], sigNN[i], sigUU[i]],
                "rate": rate,
            }
            yield arrival, key_b, json.dumps(rec, separators=(",", ":")).encode("utf-8")


# ─── Preload worker ───────────────────────────────────────────────────────────

def _categorize_missing(
    missing: list[str],
    start: dt.date,
    stop: dt.date,
    data_dir: pathlib.Path,
) -> tuple[list[str], list[str]]:
    """Split missing stations into two groups:
    - no_data: previously fetched; API returned no rows for every day in range
    - not_fetched: no arrow files and no no_data.json coverage for any day in range
    """
    no_data: list[str] = []
    not_fetched: list[str] = []
    days = set()
    d = start
    while d <= stop:
        days.add(d.isoformat())
        d += dt.timedelta(days=1)

    for gs in missing:
        tried: set[str] = set()
        # Try new JSONL format first
        jsonl_path = data_dir / gs / "no_data.jsonl"
        if jsonl_path.exists():
            for line in jsonl_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                    if d := rec.get("date"):
                        tried.add(d)
                except Exception:
                    pass
        else:
            # Fall back to legacy JSON
            old_path = data_dir / gs / "no_data.json"
            if old_path.exists():
                try:
                    tried = set(json.loads(old_path.read_bytes()).get("dates", []))
                except Exception:
                    pass
        if tried & days:   # at least one day in range was tried
            no_data.append(gs)
        else:
            not_fetched.append(gs)
    return no_data, not_fetched


def _preload_worker(
    geosncls: list[str],
    start: dt.date,
    stop: dt.date,
    data_dir: pathlib.Path,
    config: dict,
) -> None:
    try:
        apply_latency: bool = config.get("apply_latency", True)
        _set(status="preloading", error=None)
        found, missing = find_arrow_files(geosncls, start, stop, data_dir)

        total = 0
        min_arrival: int | None = None
        max_arrival: int | None = None

        for _, p in found:
            try:
                reader = ipc.open_stream(p)
                for batch in reader:
                    total += batch.num_rows
                    if batch.num_rows == 0:
                        continue
                    try:
                        schema_names = batch.schema.names
                        times = batch.column("time").to_pylist()
                        lats = (
                            batch.column("ingestLatency").to_pylist()
                            if "ingestLatency" in schema_names
                            else [0] * batch.num_rows
                        )
                        for t, lat in zip(times, lats):
                            if t is None:
                                continue
                            arr = t + (lat or 0) if apply_latency else t
                            if min_arrival is None or arr < min_arrival:
                                min_arrival = arr
                            if max_arrival is None or arr > max_arrival:
                                max_arrival = arr
                    except Exception:
                        pass
            except Exception:
                pass

        # Override start anchor with the actual first data timestamp so the
        # first message is sent immediately when replay starts, not after an
        # artificial wall-time delay equal to (data_start - user_start_param).
        if min_arrival is not None:
            config["start_data_ms"] = min_arrival
            _fmt = lambda ms: dt.datetime.fromtimestamp(ms / 1000, tz=_UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
            print(
                f"[replay] preload done — {total:,} rows  {len(found)} file(s)  "
                f"start_data={_fmt(min_arrival)}  end_data={_fmt(max_arrival) if max_arrival else '?'}",
                file=sys.stderr,
            )
        else:
            print(f"[replay] preload done — {total:,} rows  {len(found)} file(s)  (no arrival times found)", file=sys.stderr)
        if max_arrival is not None:
            config["end_data_ms"] = max_arrival

        job_id = str(uuid.uuid4())
        found_geosncls = len({gs for gs, _ in found})
        missing_no_data, missing_not_fetched = _categorize_missing(missing, start, stop, data_dir)
        _set(
            status="preloaded",
            job_id=job_id,
            files=[(gs, str(p)) for gs, p in found],
            missing_stations=missing,
            missing_no_data=missing_no_data,
            missing_not_fetched=missing_not_fetched,
            total_messages=total,
            total_geosncls=len(geosncls),
            found_geosncls=found_geosncls,
            config=config,
            sent=0,
            elapsed_ms=0,
        )
    except Exception as exc:
        _set(status="error", error=str(exc))


# ─── Replay worker ────────────────────────────────────────────────────────────

def _replay_worker(
    files: list[tuple[str, str]],
    config: dict,
    cancel: threading.Event,
) -> None:
    try:
        from confluent_kafka import Producer  # type: ignore[import-untyped]
    except ImportError:
        _set(status="error",
             error="confluent-kafka not installed. Run: pip install confluent-kafka")
        return

    apply_latency: bool  = config.get("apply_latency", True)
    time_scale: float    = float(config.get("time_scale", 1.0))
    bootstrap: str       = config.get("bootstrap_server", "localhost:9092")
    topic: str           = config.get("topic",
                               "protected.gnss.positions.shakealert.geojson.compact")
    start_data_ms: int   = config["start_data_ms"]
    end_data_ms: int     = config.get("end_data_ms", start_data_ms)
    start_wall_ms: int   = config["start_replay_wall_ms"]

    try:
        producer = Producer({
            "bootstrap.servers":         bootstrap,
            "security.protocol":         "PLAINTEXT",
            "batch.num.messages":        500,
            "linger.ms":                 10,
            # Fail fast when broker is unreachable:
            "socket.timeout.ms":         10_000,
            "request.timeout.ms":        10_000,
            "message.timeout.ms":        15_000,   # give up on each message after 15s
            "delivery.timeout.ms":       15_000,
            "reconnect.backoff.max.ms":  2_000,
            "socket.connection.setup.timeout.ms": 8_000,
        })
    except Exception as exc:
        _set(status="error", error=f"Kafka producer init failed: {exc}")
        return

    # Probe reachability: request metadata (times out quickly with settings above).
    try:
        producer.list_topics(timeout=8)
    except Exception as exc:
        _set(status="error", error=f"Kafka broker unreachable ({bootstrap}): {exc}")
        return

    total = get_state().get("total_messages", 0)
    _set(status="running", sent=0, elapsed_ms=0, error=None)

    def _ts(ms: int) -> str:
        return dt.datetime.fromtimestamp(ms / 1000, tz=_UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    print(
        f"[replay] Go — {len(files)} file(s)  {total:,} msg  "
        f"start_data={_ts(start_data_ms)}  end_data={_ts(end_data_ms)}  "
        f"scale={time_scale}×  latency={apply_latency}",
        file=sys.stderr,
    )

    # Build generators and seed the heap
    gens: dict[int, Generator] = {}
    heap: list[_HeapItem] = []
    seq = 0

    for gs, p_str in files:
        gen = _file_row_gen(pathlib.Path(p_str), gs, apply_latency)
        try:
            arrival, key_b, val_b = next(gen)
            gen_id = seq
            gens[gen_id] = gen
            heapq.heappush(heap, _HeapItem(arrival, seq, key_b, val_b, gen_id))
            seq += 1
        except StopIteration:
            pass

    if heap:
        first_arrival = heap[0].arrival_ms
        delta_s = (first_arrival - start_data_ms) / 1000.0
        print(
            f"[replay] first item arrival={_ts(first_arrival)}  "
            f"offset_from_start={delta_s:+.1f}s  heap_size={len(heap)}",
            file=sys.stderr,
        )
    else:
        print("[replay] heap is EMPTY — no data to send", file=sys.stderr)

    sent = 0
    last_update = time.monotonic()
    last_log    = time.monotonic()
    last_arrival_ms = start_data_ms

    try:
        while heap and not cancel.is_set():
            item = heapq.heappop(heap)

            replay_send_ms = start_wall_ms + int(
                (item.arrival_ms - start_data_ms) / time_scale
            )
            now_ms = int(time.time() * 1000)

            if replay_send_ms > now_ms:
                deadline = time.monotonic() + (replay_send_ms - now_ms) / 1000.0
                while True:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0 or cancel.is_set():
                        break
                    time.sleep(min(0.05, remaining))

            if cancel.is_set():
                break

            producer.produce(topic, key=item.key_b, value=item.val_b)
            producer.poll(0)
            sent += 1
            last_arrival_ms = item.arrival_ms

            now = time.monotonic()
            if now - last_update >= 1.0:
                elapsed_data_ms = last_arrival_ms - start_data_ms
                remaining_data_ms = max(0, end_data_ms - last_arrival_ms)
                _set(
                    sent=sent,
                    elapsed_ms=int(time.time() * 1000) - start_wall_ms,
                    total_messages=total,
                    current_data_time_ms=last_arrival_ms,
                    replay_elapsed_s=elapsed_data_ms / 1000.0 / time_scale,
                    replay_remaining_s=remaining_data_ms / 1000.0 / time_scale,
                )
                last_update = now

            if now - last_log >= 5.0:
                pct = 100.0 * sent / total if total else 0.0
                wall_elapsed = int(time.time() * 1000) - start_wall_ms
                print(
                    f"[replay]   {sent:,}/{total:,} ({pct:.1f}%)  "
                    f"data_time={_ts(last_arrival_ms)}  "
                    f"wall={wall_elapsed/1000:.0f}s",
                    file=sys.stderr,
                )
                last_log = now

            gen = gens.get(item.gen_id)
            if gen is not None:
                try:
                    arrival, key_b, val_b = next(gen)
                    heapq.heappush(heap, _HeapItem(arrival, seq, key_b, val_b, item.gen_id))
                    seq += 1
                except StopIteration:
                    del gens[item.gen_id]

        # Flush in small increments so the cancel event can bail out promptly.
        # producer.flush(timeout) returns the number of messages still in-queue.
        flush_deadline = time.monotonic() + 20.0
        while time.monotonic() < flush_deadline and not cancel.is_set():
            n_left = producer.flush(timeout=0.5)
            if n_left == 0:
                break

        elapsed = int(time.time() * 1000) - start_wall_ms
        if cancel.is_set():
            _set(status="canceled", sent=sent, elapsed_ms=elapsed)
        else:
            _set(status="done", sent=sent, elapsed_ms=elapsed, total_messages=total)

    except Exception as exc:
        _set(status="error", error=str(exc), sent=sent)


# ─── Public API (called from webserver / CLI) ─────────────────────────────────

def start_preload(
    geosncls: list[str],
    start: dt.date,
    stop: dt.date,
    data_dir: pathlib.Path,
    config: dict,
) -> bool:
    """Start background preload. Returns False if a replay is already in progress."""
    global _preload_thread
    with _lock:
        status = _state.get("status", "idle")
        if status in ("preloading", "running", "starting"):
            return False
    t = threading.Thread(
        target=_preload_worker,
        args=(geosncls, start, stop, data_dir, config),
        daemon=True,
        name="replay-preload",
    )
    _preload_thread = t
    t.start()
    return True


def start_replay(job_id: str) -> bool:
    """Kick off the replay. Returns False if state is not preloaded or job_id wrong."""
    global _replay_thread
    with _lock:
        if _state.get("status") != "preloaded":
            return False
        if _state.get("job_id") != job_id:
            return False
        files  = list(_state.get("files", []))
        config = dict(_state.get("config", {}))
        config["start_replay_wall_ms"] = int(time.time() * 1000)
        _state["config"] = config
        _state["status"] = "starting"

    _cancel.clear()
    t = threading.Thread(
        target=_replay_worker,
        args=(files, config, _cancel),
        daemon=True,
        name="replay-run",
    )
    _replay_thread = t
    t.start()
    return True


def cancel_replay(job_id: str | None = None) -> bool:
    """Cancel a running or preloaded replay.

    Returns True when the cancel is accepted (including when the replay is already
    in a terminal state — done/canceled/error — so the caller never gets a spurious
    409).  Returns False only when the job_id doesn't match.
    """
    with _lock:
        status = _state.get("status")
        if job_id is not None and _state.get("job_id") != job_id:
            return False
        if status == "preloaded":
            # Wasn't running yet — just reset to idle so the caller can re-preload.
            _state.clear()
            _state["status"] = "idle"
            return True
        if status in ("done", "canceled", "error", "idle"):
            # Already terminal — nothing to do, but don't report a spurious error.
            return True
        if status not in ("running", "starting"):
            return False
    _cancel.set()
    return True


def start_preloaded() -> bool:
    """Start the currently-preloaded replay without requiring the caller to know the job_id.

    Returns False if nothing is preloaded or a replay is already running.
    """
    global _replay_thread
    with _lock:
        if _state.get("status") != "preloaded":
            return False
        files  = list(_state.get("files", []))
        config = dict(_state.get("config", {}))
        config["start_replay_wall_ms"] = int(time.time() * 1000)
        _state["config"] = config
        _state["status"] = "starting"

    _cancel.clear()
    t = threading.Thread(
        target=_replay_worker,
        args=(files, config, _cancel),
        daemon=True,
        name="replay-run",
    )
    _replay_thread = t
    t.start()
    return True


def reset() -> None:
    """Return to idle (no-op if replay is active)."""
    with _lock:
        if _state.get("status") in ("preloading", "running", "starting"):
            return
        _state.clear()
        _state["status"] = "idle"


# ─── Synchronous CLI entry point ──────────────────────────────────────────────

def run_cli(
    geosncls: list[str],
    start: dt.date,
    stop: dt.date,
    data_dir: pathlib.Path,
    bootstrap_server: str,
    topic: str,
    time_scale: float,
    apply_latency: bool,
    job_id: str | None = None,
    verbose: bool = True,
) -> None:
    """Run preload + replay synchronously (for CLI use). Ctrl-C cancels."""
    import sys

    if verbose:
        print(f"Preloading {len(geosncls)} station(s) "
              f"{start} → {stop} …", file=sys.stderr)

    found, missing = find_arrow_files(geosncls, start, stop, data_dir)
    if missing and verbose:
        print(f"  ⚠  {len(missing)} station(s) have no data in range:", file=sys.stderr)
        for gs in missing[:20]:
            print(f"       {gs}", file=sys.stderr)
        if len(missing) > 20:
            print(f"       … and {len(missing)-20} more", file=sys.stderr)

    if not found:
        print("No data found — aborting.", file=sys.stderr)
        return

    total = 0
    for _, p in found:
        try:
            reader = ipc.open_stream(p)
            for batch in reader:
                total += batch.num_rows
        except Exception:
            pass

    if verbose:
        print(f"  {len(found)} file(s), {total:,} rows total", file=sys.stderr)
        print(f"  bootstrap : {bootstrap_server}", file=sys.stderr)
        print(f"  topic     : {topic}", file=sys.stderr)
        print(f"  time_scale: {time_scale}×  apply_latency={apply_latency}", file=sys.stderr)

    start_data_ms = int(
        dt.datetime(start.year, start.month, start.day, tzinfo=_UTC).timestamp() * 1000
    )
    config = {
        "bootstrap_server":    bootstrap_server,
        "topic":               topic,
        "time_scale":          time_scale,
        "apply_latency":       apply_latency,
        "start_data_ms":       start_data_ms,
        "start_replay_wall_ms": int(time.time() * 1000),
    }

    cancel_ev = threading.Event()
    thread = threading.Thread(
        target=_replay_worker,
        args=([(gs, str(p)) for gs, p in found], config, cancel_ev),
        daemon=True,
    )
    thread.start()

    try:
        while thread.is_alive():
            time.sleep(0.5)
            if verbose:
                s = get_state()
                sent  = s.get("sent", 0)
                elaps = s.get("elapsed_ms", 0)
                print(
                    f"\r  sent {sent:>8,} / {total:,}  "
                    f"({elaps/1000:.0f}s elapsed)   ",
                    end="",
                    file=sys.stderr,
                )
    except KeyboardInterrupt:
        print("\nCancelling …", file=sys.stderr)
        cancel_ev.set()
        thread.join(timeout=5)
    else:
        thread.join()
        print("", file=sys.stderr)

    s = get_state()
    if verbose:
        print(f"Status: {s.get('status')}  sent={s.get('sent',0):,}", file=sys.stderr)

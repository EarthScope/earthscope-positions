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

import pyarrow.compute as pc
import pyarrow.ipc as ipc

_UTC = dt.timezone.utc

# ─── Singleton state ──────────────────────────────────────────────────────────

_lock = threading.Lock()
_state: dict[str, Any] = {"status": "idle"}
_preload_thread: threading.Thread | None = None
_replay_thread: threading.Thread | None = None
_cancel = threading.Event()

_LOG_MAX = 300  # keep at most this many status-log lines in state

# ─── Delivery-check reader ─────────────────────────────────────────────────────
# The reader that verifies "we can read what we write" runs in a SEPARATE
# PROCESS (its own GIL), so its high-rate polling can never contend with — or
# starve — the web server's asyncio event loop.  It reports counters back through
# a shared-memory Array; a light monitor thread mirrors them into the replay
# state.  Round-trip latency is derived from each message's Kafka timestamp (set
# at produce time) vs. the local wall clock (same machine → comparable), so no
# cross-process message bookkeeping is needed.
import multiprocessing as _mp

_consumer_proc = None                          # multiprocessing.Process | None
_consumer_stop = None                          # mp.Event | None (stops the reader process)
_consumer_stats = None                         # mp.Array('d', 4): [read, matched, sum_lat_ms, last_read_ms]
_consumer_monitor: threading.Thread | None = None
_monitor_stop = threading.Event()

# ── Hot standby ────────────────────────────────────────────────────────────────
# To make "Go" start writing with near-zero delay, the Kafka producer is
# connected and the delivery-check consumer is spawned+positioned during PRELOAD
# (not at Go), and the messages are materialized into an in-memory list ready to
# fire.  These globals hold that pre-established state between preload and Go.
_producer = None                               # confluent_kafka.Producer | None (hot)
_producer_key: tuple[str, str] | None = None   # (bootstrap, topic) the producer is bound to
_prepared_messages: list[tuple[int, bytes, bytes]] | None = None  # sorted (arrival_ms, key, val)

# Never materialize more than this many messages in memory (guards a whole-day,
# all-stations replay from exhausting RAM); above it, fall back to lazy streaming.
_MAX_MATERIALIZE = 3_000_000

# When "select by arrival time" is on, read this many seconds of data *before*
# the window start so records whose data timestamp precedes the window but whose
# arrival (data_time + latency) lands inside it are still captured.
_PREBUFFER_S = 30

# Signalled the instant the first message is produced, so callers (e.g. the curl
# `start` endpoint) can measure the delay between the start request and the first
# actual write, for synchronization.
_first_write_event = threading.Event()

# Staleness thresholds for "haven't seen our own writes echoed" (seconds).
_ECHO_WARN_S = 2.0
_ECHO_ERROR_S = 5.0


def get_state() -> dict[str, Any]:
    with _lock:
        s = dict(_state)
        # Return a copy of the log so callers can't mutate the shared list.
        if isinstance(s.get("log"), list):
            s["log"] = list(s["log"])
        return s


def _set(**kw: Any) -> None:
    with _lock:
        _state.update(kw)


def _log(msg: str, level: str = "info") -> None:
    """Append a line to the replay status log (surfaced on the web UI) and echo
    it to stderr for CLI/server operators.

    level is one of "info", "warn", "error" — the web UI colours accordingly.
    """
    entry = {"ts": int(time.time() * 1000), "level": level, "msg": msg}
    with _lock:
        log = _state.get("log")
        if not isinstance(log, list):
            log = []
            _state["log"] = log
        log.append(entry)
        if len(log) > _LOG_MAX:
            del log[: len(log) - _LOG_MAX]
    print(f"[replay] {msg}", file=sys.stderr)


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
    win_start_ms: int | None = None,
    win_stop_ms: int | None = None,
    select_by_arrival: bool = False,
    output_format: str = "compact",
) -> Generator[tuple[int, bytes, bytes], None, None]:
    """Yield (arrival_ms, key_bytes, value_bytes) lazily, one batch at a time.

    ``output_format`` controls the JSON payload written per message:
    - "compact"  — compact one-line record (default):
        {"time":..,"Q":..,"type":"ENU","SNCL":"..","coor":[E,N,U],
         "err":[Ee,Ne,Ue],"rate":r}
    - "geojson"  — one GeoJSON Feature per sample:
        {"type":"Feature","geometry":{"type":"Point","coordinates":[E,N,U]},
         "properties":{"coordinateType":"ENU","SNCL":"..","time":..,
                       "EError":..,"NError":..,"UError":..,"quality":..,
                       "sampleRate":r}}

    Reads Arrow IPC batches on demand so the first next() call is fast — only
    the first batch is read, not the entire file.  GNSS position files are
    already time-sorted, so no cross-batch sort is needed.

    Windowing:
    - Normally, only rows whose **data time** is within [win_start_ms, win_stop_ms]
      are emitted.
    - When ``select_by_arrival`` (with ``apply_latency``), rows are selected by
      **arrival time** (data_time + ingestLatency) instead — so a record whose
      timestamp precedes the window but which would have *arrived* inside it is
      included, and one whose timestamp is inside the window but which would have
      arrived after ``win_stop_ms`` is dropped.

    Either way, rows are data-time-sorted and arrival >= data_time, so once a
    batch's earliest data time is past win_stop we can stop reading.
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

        # Trim the batch to the window in Arrow (C) BEFORE converting to Python
        # lists — otherwise seeding 200+ whole-day files to_pylist() hogs the GIL
        # for many seconds and stalls both the first write and the web UI.
        if win_start_ms is not None or win_stop_ms is not None:
            tcol = batch.column("time")
            # Rows are data-time-sorted and arrival >= data_time, so if this whole
            # batch is past the window (by data time) nothing further can qualify.
            if win_stop_ms is not None:
                bmin = pc.min(tcol).as_py()
                if bmin is not None and bmin > win_stop_ms:
                    return
            # Choose the column the window applies to: arrival vs. data time.
            if select_by_arrival and apply_latency and "ingestLatency" in batch.schema.names:
                sel = pc.add(tcol, pc.fill_null(batch.column("ingestLatency"), 0))
            else:
                sel = tcol
            mask = None
            if win_start_ms is not None:
                mask = pc.greater_equal(sel, win_start_ms)
            if win_stop_ms is not None:
                m2 = pc.less_equal(sel, win_stop_ms)
                mask = m2 if mask is None else pc.and_(mask, m2)
            if mask is not None:
                batch = batch.filter(mask)
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
            # Window selection was already applied at the Arrow level above (by
            # data time, or by arrival time when select_by_arrival) — don't
            # re-filter here, or arrival-mode rows with t < win_start would be
            # wrongly dropped.
            lat     = lats[i] or 0
            arrival = t + lat if apply_latency else t
            if output_format == "geojson":
                rec = {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [east[i], north[i], up[i]]},
                    "properties": {
                        "coordinateType": "ENU",
                        "SNCL":       geosncl,
                        "time":       t,
                        "EError":     sigEE[i],
                        "NError":     sigNN[i],
                        "UError":     sigUU[i],
                        "quality":    q_col[i],
                        "sampleRate": rate,
                    },
                }
            else:
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
        # Any prior hot-standby (producer/consumer/materialized list) belongs to a
        # previous preload — tear it down before establishing a fresh one.
        _teardown_hot_standby()

        # Fresh log for this run.
        _set(status="preloading", error=None, log=[])

        # Intra-day time window (epoch ms) — only rows in [win_start, win_stop]
        # count toward the replay, so a 2-minute selection isn't a whole-day run.
        win_start = config.get("window_start_ms")
        win_stop  = config.get("window_stop_ms")

        # "Select by arrival time": window applies to arrival (data_time+latency),
        # and we read a pre-buffer of data before the window start so late records
        # whose timestamp precedes the window but whose arrival lands inside it are
        # captured.  Only meaningful when latency is being applied.
        select_by_arrival = bool(config.get("select_by_arrival", False)) and apply_latency
        config["select_by_arrival"] = select_by_arrival

        read_start = start
        if select_by_arrival and win_start is not None:
            read_start = dt.datetime.fromtimestamp(
                (win_start - _PREBUFFER_S * 1000) / 1000, tz=_UTC
            ).date()

        _log(
            f"Preloading {len(geosncls)} station(s)  {read_start} → {stop} …"
            + (f"  (arrival-time window, {_PREBUFFER_S}s pre-buffer)" if select_by_arrival else "")
        )
        found, missing = find_arrow_files(geosncls, read_start, stop, data_dir)
        if missing:
            _log(f"{len(missing)} station(s) have no Arrow data in range", "warn")

        total = 0
        min_arrival: int | None = None
        max_arrival: int | None = None

        for _, p in found:
            try:
                reader = ipc.open_stream(p)
                for batch in reader:
                    if batch.num_rows == 0:
                        continue
                    try:
                        tcol = batch.column("time")
                        # Sorted by data time; arrival >= data time, so once a
                        # batch is entirely past win_stop nothing further qualifies.
                        if win_stop is not None:
                            bmin = pc.min(tcol).as_py()
                            if bmin is not None and bmin > win_stop:
                                break
                        if apply_latency and "ingestLatency" in batch.schema.names:
                            arr = pc.add(tcol, pc.fill_null(batch.column("ingestLatency"), 0))
                        else:
                            arr = tcol
                        sel = arr if select_by_arrival else tcol
                        mask = None
                        if win_start is not None:
                            mask = pc.greater_equal(sel, win_start)
                        if win_stop is not None:
                            m2 = pc.less_equal(sel, win_stop)
                            mask = m2 if mask is None else pc.and_(mask, m2)
                        arr_f = arr.filter(mask) if mask is not None else arr
                        nrows = len(arr_f)
                        if nrows == 0:
                            continue
                        total += nrows
                        bmn = pc.min(arr_f).as_py()
                        bmx = pc.max(arr_f).as_py()
                        if bmn is not None:
                            min_arrival = bmn if min_arrival is None else min(min_arrival, bmn)
                        if bmx is not None:
                            max_arrival = bmx if max_arrival is None else max(max_arrival, bmx)
                    except Exception:
                        pass
            except Exception:
                pass

        # Override start anchor with the actual first arrival so the first message
        # is sent immediately when replay starts, not after an artificial
        # wall-time delay equal to (data_start - user_start_param).
        _fmt = lambda ms: dt.datetime.fromtimestamp(ms / 1000, tz=_UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        if min_arrival is not None:
            config["start_data_ms"] = min_arrival
            _log(
                f"Preload done — {total:,} rows  {len(found)} file(s)  "
                f"start_data={_fmt(min_arrival)}  end_data={_fmt(max_arrival) if max_arrival else '?'}"
            )
        else:
            _log(f"Preload done — {total:,} rows  {len(found)} file(s)  (no arrival times found)", "warn")
        if max_arrival is not None:
            config["end_data_ms"] = max_arrival

        files_list = [(gs, str(p)) for gs, p in found]

        # ── Hot standby: connect the producer and spawn+position the delivery-check
        #    consumer NOW, and materialize the messages into memory, so "Go" starts
        #    writing with near-zero delay. ────────────────────────────────────────
        bootstrap = config.get("bootstrap_server", "localhost:9092")
        topic     = config.get("topic", "protected.gnss.positions.shakealert.geojson.compact")
        _start_hot_standby(bootstrap, topic)
        _prepare_messages(files_list, config, total)

        job_id = str(uuid.uuid4())
        found_geosncls = len({gs for gs, _ in found})
        missing_no_data, missing_not_fetched = _categorize_missing(missing, read_start, stop, data_dir)
        _set(
            status="preloaded",
            job_id=job_id,
            files=files_list,
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
        _log(f"Preload failed: {exc}", "error")
        _set(status="error", error=str(exc))


# ─── Delivery-check reader (separate process) ──────────────────────────────────

def _consumer_process(bootstrap: str, topic: str, stats, stop_evt, ready_evt) -> None:
    """Runs in a SEPARATE PROCESS (own GIL — cannot starve the web event loop).

    Reads *topic* from its current end and writes running counters into the
    shared ``stats`` array ``[read, matched, sum_latency_ms, last_read_ms]``.
    Round-trip latency = local wall clock − each message's Kafka timestamp (the
    produce time), which is valid because both are on the same machine.
    """
    import time as _t

    try:
        from confluent_kafka import Consumer, TopicPartition  # type: ignore[import-untyped]
    except Exception:
        ready_evt.set()
        return

    import uuid as _uuid
    consumer = Consumer({
        "bootstrap.servers":  bootstrap,
        "security.protocol":  "PLAINTEXT",
        "group.id":           f"es-pos-replay-check-{_uuid.uuid4()}",
        "enable.auto.commit": False,
        "auto.offset.reset":  "latest",
        "socket.timeout.ms":  10_000,
        "session.timeout.ms": 10_000,
    })

    try:
        md = consumer.list_topics(topic, timeout=10)
        parts = list(md.topics[topic].partitions.keys()) if topic in md.topics else []
        tps = [TopicPartition(topic, p) for p in parts]
        consumer.assign(tps)
        for p in parts:
            _lo, hi = consumer.get_watermark_offsets(
                TopicPartition(topic, p), timeout=10, cached=False
            )
            consumer.seek(TopicPartition(topic, p, hi))
    except Exception:
        try:
            consumer.subscribe([topic])
        except Exception:
            ready_evt.set()
            consumer.close()
            return
    finally:
        ready_evt.set()

    read = 0
    matched = 0
    sum_lat = 0.0
    last_read = 0.0
    try:
        while not stop_evt.is_set():
            msgs = consumer.consume(num_messages=2000, timeout=0.5)
            if not msgs:
                continue
            now_ms = _t.time() * 1000.0
            for m in msgs:
                if m is None or m.error():
                    continue
                read += 1
                try:
                    _tstype, tsval = m.timestamp()
                except Exception:
                    tsval = None
                if tsval and tsval > 0:
                    lat = now_ms - tsval
                    if lat >= 0:
                        matched += 1
                        sum_lat += lat
                last_read = now_ms
            with stats.get_lock():
                stats[0] = float(read)
                stats[1] = float(matched)
                stats[2] = sum_lat
                stats[3] = last_read
    finally:
        try:
            consumer.close()
        except Exception:
            pass


def _consumer_monitor_worker(stats, stop: threading.Event) -> None:
    """Mirror the reader process's shared counters into the replay state and
    classify echo staleness.  Lightweight: wakes every 0.4 s."""
    while not stop.is_set():
        with stats.get_lock():
            read = int(stats[0])
            matched = int(stats[1])
            sum_lat = stats[2]
            last_read = stats[3]

        st = get_state()
        written = int(st.get("sent", 0))
        now_ms = time.time() * 1000.0
        ref = last_read if last_read > 0 else float(st.get("first_write_ms") or 0)

        outstanding = written - matched
        if written == 0 or outstanding <= 0 or not ref:
            status, message = "ok", None
        else:
            age = (now_ms - ref) / 1000.0
            if age >= _ECHO_ERROR_S:
                status, message = "error", f"No echo of written data for {age:.1f}s — is the consumer/broker healthy?"
            elif age >= _ECHO_WARN_S:
                status, message = "warn", f"Echo lagging {age:.1f}s behind writes."
            else:
                status, message = "ok", None

        _set(
            consumer_read=read,
            consumer_matched=matched,
            consumer_unmatched=max(0, written - matched),
            consumer_mean_rt_ms=(sum_lat / matched) if matched else None,
            consumer_status=status,
            consumer_message=message,
        )
        stop.wait(0.4)


# ─── Hot standby (producer + consumer + materialized messages) ─────────────────

def _connect_producer(bootstrap: str):
    """Create a Kafka Producer and probe reachability.  Raises on failure."""
    from confluent_kafka import Producer  # type: ignore[import-untyped]

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
    # Probe reachability: request metadata (times out quickly with settings above).
    producer.list_topics(timeout=8)
    return producer


def _start_consumer(bootstrap: str, topic: str) -> bool:
    """Spawn the delivery-check reader process (positioned at the topic's end) and
    its monitor thread.  Returns True if it reported ready.  Idempotent-ish: any
    prior consumer should be stopped via _stop_consumer() first."""
    global _consumer_proc, _consumer_stop, _consumer_stats, _consumer_monitor
    try:
        ctx = _mp.get_context("spawn")
        _consumer_stats = ctx.Array("d", 4)      # [read, matched, sum_lat_ms, last_read_ms]
        _consumer_stop = ctx.Event()
        ready_evt = ctx.Event()
        _consumer_proc = ctx.Process(
            target=_consumer_process,
            args=(bootstrap, topic, _consumer_stats, _consumer_stop, ready_evt),
            daemon=True,
            name="replay-consumer",
        )
        _consumer_proc.start()
        _monitor_stop.clear()
        _consumer_monitor = threading.Thread(
            target=_consumer_monitor_worker,
            args=(_consumer_stats, _monitor_stop),
            daemon=True,
            name="replay-consumer-monitor",
        )
        _consumer_monitor.start()
        return bool(ready_evt.wait(timeout=20))
    except Exception as exc:
        _consumer_proc = None
        _log(f"Delivery-check reader could not start ({exc}); continuing without it.", "warn")
        return False


def _start_hot_standby(bootstrap: str, topic: str) -> bool:
    """Connect the producer and spawn+position the delivery-check consumer during
    PRELOAD so "Go" starts writing with near-zero delay.  Returns True if the
    producer connected (the consumer is best-effort).  On failure (e.g. Kafka not
    running yet) it logs a warning and returns False; the replay will then connect
    lazily at Go, as before."""
    global _producer, _producer_key
    try:
        _producer = _connect_producer(bootstrap)
        _producer_key = (bootstrap, topic)
    except ImportError:
        _log("confluent-kafka not installed. Run: pip install confluent-kafka", "error")
        return False
    except Exception as exc:
        _producer = None
        _producer_key = None
        _log(f"Hot standby: Kafka not reachable at preload ({bootstrap}: {exc}); "
             f"will connect when you press Go.", "warn")
        return False

    if _start_consumer(bootstrap, topic):
        _log(f"Hot standby ready — producer connected to {bootstrap}, "
             f"delivery-check reader positioned at end of {topic!r}.")
    else:
        _log(f"Hot standby: producer connected to {bootstrap}; delivery-check "
             f"reader slow to start (will still be used).", "warn")
    return True


def _teardown_hot_standby() -> None:
    """Flush+close the hot producer, stop the consumer, and drop the materialized
    message list.  Safe to call when nothing is established."""
    global _producer, _producer_key, _prepared_messages
    p = _producer
    if p is not None:
        try:
            p.flush(timeout=2.0)
        except Exception:
            pass
    _producer = None
    _producer_key = None
    _prepared_messages = None
    _stop_consumer()


def _prepare_messages(files: list[tuple[str, str]], config: dict, total: int) -> None:
    """Materialize all messages into a single arrival-sorted in-memory list so
    "Go" can start writing immediately (no per-file Arrow reads on the hot path).

    Skipped (leaving lazy streaming in place) when the message count exceeds
    _MAX_MATERIALIZE, to bound memory on huge (e.g. whole-day, all-station) runs.
    """
    global _prepared_messages
    _prepared_messages = None
    if total <= 0 or total > _MAX_MATERIALIZE:
        if total > _MAX_MATERIALIZE:
            _log(f"{total:,} messages exceeds the in-memory cap "
                 f"({_MAX_MATERIALIZE:,}); will stream from disk at Go.", "warn")
        return
    apply_latency: bool = config.get("apply_latency", True)
    win_start_ms = config.get("window_start_ms")
    win_stop_ms  = config.get("window_stop_ms")
    select_by_arrival = bool(config.get("select_by_arrival", False))
    output_format = config.get("output_format", "compact")
    try:
        msgs: list[tuple[int, bytes, bytes]] = []
        for gs, p_str in files:
            for arrival, key_b, val_b in _file_row_gen(
                pathlib.Path(p_str), gs, apply_latency,
                win_start_ms, win_stop_ms, select_by_arrival, output_format,
            ):
                msgs.append((arrival, key_b, val_b))
        # Stable sort by arrival — ties keep insertion (per-file) order.
        msgs.sort(key=lambda m: m[0])
        _prepared_messages = msgs
        _log(f"Prepared {len(msgs):,} message(s) in memory — ready to write instantly.")
    except Exception as exc:
        _prepared_messages = None
        _log(f"Could not pre-build message list ({exc}); will stream from disk at Go.", "warn")


def _heap_merge(
    files: list[tuple[str, str]],
    apply_latency: bool,
    win_start_ms: int | None,
    win_stop_ms: int | None,
    select_by_arrival: bool,
    output_format: str = "compact",
) -> Generator[tuple[int, bytes, bytes], None, None]:
    """Lazily merge per-file generators into one arrival-ordered stream."""
    gens: dict[int, Generator] = {}
    heap: list[_HeapItem] = []
    seq = 0
    for gs, p_str in files:
        gen = _file_row_gen(
            pathlib.Path(p_str), gs, apply_latency,
            win_start_ms, win_stop_ms, select_by_arrival, output_format,
        )
        try:
            arrival, key_b, val_b = next(gen)
            gens[seq] = gen
            heapq.heappush(heap, _HeapItem(arrival, seq, key_b, val_b, seq))
            seq += 1
        except StopIteration:
            pass
    while heap:
        item = heapq.heappop(heap)
        yield item.arrival_ms, item.key_b, item.val_b
        gen = gens.get(item.gen_id)
        if gen is not None:
            try:
                arrival, key_b, val_b = next(gen)
                heapq.heappush(heap, _HeapItem(arrival, seq, key_b, val_b, item.gen_id))
                seq += 1
            except StopIteration:
                del gens[item.gen_id]


# ─── Replay worker ────────────────────────────────────────────────────────────

def _replay_worker(
    files: list[tuple[str, str]],
    config: dict,
    cancel: threading.Event,
) -> None:
    global _producer, _producer_key

    apply_latency: bool  = config.get("apply_latency", True)
    time_scale: float    = float(config.get("time_scale", 1.0))
    bootstrap: str       = config.get("bootstrap_server", "localhost:9092")
    topic: str           = config.get("topic",
                               "protected.gnss.positions.shakealert.geojson.compact")
    start_data_ms: int   = config["start_data_ms"]
    end_data_ms: int     = config.get("end_data_ms", start_data_ms)
    start_wall_ms: int   = config["start_replay_wall_ms"]
    win_start_ms         = config.get("window_start_ms")
    win_stop_ms          = config.get("window_stop_ms")
    select_by_arrival    = bool(config.get("select_by_arrival", False))
    output_format        = config.get("output_format", "compact")

    # Reuse the hot-standby producer if it's bound to this same broker+topic;
    # otherwise connect now (fallback path when Kafka wasn't up at preload).
    if _producer is not None and _producer_key == (bootstrap, topic):
        producer = _producer
        _log(f"Using hot-standby producer for {bootstrap} → topic {topic!r} (0 ms connect).")
    else:
        _log(f"Connecting to Kafka broker {bootstrap} …")
        try:
            producer = _connect_producer(bootstrap)
        except ImportError:
            msg = "confluent-kafka not installed. Run: pip install confluent-kafka"
            _log(msg, "error")
            _set(status="error", error=msg)
            _first_write_event.set()
            return
        except Exception as exc:
            msg = f"Kafka broker unreachable ({bootstrap}): {exc}"
            _log(msg, "error")
            _log("Is Kafka running? Check the bootstrap server address.", "error")
            _set(status="error", error=msg)
            _first_write_event.set()
            return
        _producer = producer
        _producer_key = (bootstrap, topic)
        _log(f"Connected to {bootstrap} — starting replay to topic {topic!r}")

    total = get_state().get("total_messages", 0)
    _set(status="running", sent=0, elapsed_ms=0, error=None,
         start_requested_ms=start_wall_ms, first_write_ms=None, startup_delay_ms=None,
         consumer_read=0, consumer_matched=0, consumer_unmatched=0,
         consumer_mean_rt_ms=None, consumer_status="ok", consumer_message=None)

    # ── Delivery-check reader: reuse the hot-standby one if alive, else start it
    #    now (positioned at the topic's end) BEFORE producing. ───────────────────
    _first_write_event.clear()
    if _consumer_proc is not None and _consumer_proc.is_alive():
        _log("Delivery-check reader (hot standby) already positioned at topic end.")
    else:
        if _start_consumer(bootstrap, topic):
            _log("Delivery-check reader (separate process) positioned at topic end.")
        else:
            _log("Delivery-check reader slow to start; continuing anyway.", "warn")

    def _ts(ms: int) -> str:
        return dt.datetime.fromtimestamp(ms / 1000, tz=_UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Message source: the materialized list (instant) if prepared at preload,
    # else a lazy heap-merge over the Arrow files.
    if _prepared_messages is not None:
        source: Generator[tuple[int, bytes, bytes], None, None] = iter(_prepared_messages)
        n_src = len(_prepared_messages)
    else:
        source = _heap_merge(files, apply_latency, win_start_ms, win_stop_ms,
                             select_by_arrival, output_format)
        n_src = total

    _log(
        f"Go — {len(files)} file(s)  {total:,} msg  "
        f"start_data={_ts(start_data_ms)}  end_data={_ts(end_data_ms)}  "
        f"scale={time_scale}×  latency={apply_latency}  "
        f"select_by_arrival={select_by_arrival}  format={output_format}"
    )

    sent = 0
    last_update = time.monotonic()
    last_log    = time.monotonic()
    last_arrival_ms = start_data_ms
    first_logged = False

    try:
        for arrival_ms, key_b, val_b in source:
            if cancel.is_set():
                break

            if not first_logged:
                delta_s = (arrival_ms - start_data_ms) / 1000.0
                _log(
                    f"First item arrival={_ts(arrival_ms)}  "
                    f"offset_from_start={delta_s:+.1f}s  queued={n_src:,}"
                )
                first_logged = True

            replay_send_ms = start_wall_ms + int(
                (arrival_ms - start_data_ms) / time_scale
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

            now_wall_ms = int(time.time() * 1000)

            # On the very first message, record the delay between the start
            # request and the first actual write (for synchronization).
            if sent == 0:
                _set(first_write_ms=now_wall_ms, startup_delay_ms=now_wall_ms - start_wall_ms)
                _first_write_event.set()
                _log(f"First write — {now_wall_ms - start_wall_ms} ms after the start request.")

            # Stamp each message with the produce time so the delivery-check
            # reader can measure the added round-trip latency from msg.timestamp().
            producer.produce(topic, key=key_b, value=val_b, timestamp=now_wall_ms)
            producer.poll(0)
            sent += 1

            # Yield the GIL periodically so a fast (unpaced) send burst can't
            # starve the web server's event loop.
            if sent % 500 == 0:
                time.sleep(0)
            last_arrival_ms = arrival_ms

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
                _log(
                    f"{sent:,}/{total:,} ({pct:.1f}%)  "
                    f"data_time={_ts(last_arrival_ms)}  "
                    f"wall={wall_elapsed/1000:.0f}s"
                )
                last_log = now

        if sent == 0 and not cancel.is_set():
            _log("No data to send — nothing matched the window.", "warn")

        # Flush in small increments so the cancel event can bail out promptly.
        # producer.flush(timeout) returns the number of messages still in-queue.
        flush_deadline = time.monotonic() + 20.0
        while time.monotonic() < flush_deadline and not cancel.is_set():
            n_left = producer.flush(timeout=0.5)
            if n_left == 0:
                break

        # Give the delivery-check reader a moment to catch up with the final
        # messages, then report and stop it.
        _drain_consumer(sent, cancel)
        _stop_consumer()

        cs = get_state()
        matched = cs.get("consumer_matched", 0)
        rt = cs.get("consumer_mean_rt_ms")
        rt_str = f"{rt:.1f} ms" if isinstance(rt, (int, float)) else "n/a"
        _log(
            f"Delivery check — wrote {sent:,}, read back {cs.get('consumer_read', 0):,}, "
            f"matched {matched:,}/{sent:,}; mean round-trip {rt_str}."
        )

        elapsed = int(time.time() * 1000) - start_wall_ms
        if cancel.is_set():
            stopped = int(time.time() * 1000)
            creq = get_state().get("cancel_requested_ms")
            cd = (stopped - creq) if isinstance(creq, (int, float)) else None
            _log(
                f"Canceled — {sent:,} message(s) sent in {elapsed/1000:.0f}s"
                + (f"; stop took {cd} ms after cancel request" if cd is not None else ""),
                "warn",
            )
            _set(status="canceled", sent=sent, elapsed_ms=elapsed,
                 stopped_ms=stopped, cancel_delay_ms=cd)
        else:
            _log(f"Done — {sent:,} message(s) sent in {elapsed/1000:.0f}s")
            _set(status="done", sent=sent, elapsed_ms=elapsed, total_messages=total)

    except Exception as exc:
        _log(f"Replay failed: {exc}", "error")
        _set(status="error", error=str(exc), sent=sent)
    finally:
        # The replay is over — release the hot standby entirely (producer +
        # consumer + materialized list).  The next preload re-establishes it.
        _teardown_hot_standby()
        _first_write_event.set()   # release any start-endpoint waiter


def _drain_consumer(sent: int, cancel: threading.Event, grace_s: float = 6.0) -> None:
    """Wait briefly for the reader to echo the last messages (via shared stats)."""
    if _consumer_stats is None:
        return
    deadline = time.monotonic() + grace_s
    while time.monotonic() < deadline:
        with _consumer_stats.get_lock():
            read = int(_consumer_stats[0])
        if read >= sent:
            break
        if cancel.is_set():
            break
        time.sleep(0.2)


def _stop_consumer() -> None:
    """Stop the reader process and its monitor thread."""
    if _consumer_stop is not None:
        _consumer_stop.set()
    _monitor_stop.set()
    p = _consumer_proc
    if p is not None:
        p.join(timeout=5.0)
        if p.is_alive():
            try:
                p.terminate()
            except Exception:
                pass
    t = _consumer_monitor
    if t is not None:
        t.join(timeout=2.0)


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
        _state["start_requested_ms"] = config["start_replay_wall_ms"]

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
            # Wasn't running yet — reset to idle so the caller can re-preload.
            _state.clear()
            _state["status"] = "idle"
        elif status in ("done", "canceled", "error", "idle"):
            # Already terminal — nothing to do, but don't report a spurious error.
            return True
        elif status not in ("running", "starting"):
            return False
    if status == "preloaded":
        # Release the hot standby OUTSIDE the lock (teardown joins threads/procs
        # that themselves take _lock via get_state()).
        _teardown_hot_standby()
        return True
    _set(cancel_requested_ms=int(time.time() * 1000))
    _cancel.set()
    return True


def wait_first_write(timeout: float = 30.0) -> dict:
    """Block until the first message is written (or *timeout*), then return the
    start→first-write timing.  Used by the `start` endpoint so a curl trigger
    learns exactly when — and how long after the request — data began flowing."""
    started = _first_write_event.wait(timeout=timeout)
    s = get_state()
    return {
        "started_writing": bool(started) and s.get("first_write_ms") is not None,
        "start_requested_ms": s.get("start_requested_ms"),
        "first_write_ms": s.get("first_write_ms"),
        "startup_delay_ms": s.get("startup_delay_ms"),
    }


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
        _state["start_requested_ms"] = config["start_replay_wall_ms"]

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
    # Release any hot standby left over from a preloaded/terminal replay
    # (outside the lock — teardown joins threads that take _lock).
    _teardown_hot_standby()


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

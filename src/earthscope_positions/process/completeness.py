"""
Generate 15-minute completeness and latency summary Arrow files from position data.

For each source .arrow file:
    <stem>.completeness.arrow is written in the same directory.

Output schema
-------------
  bucket_start_ms          int64    UTC epoch ms for the bin's start (inclusive)
  row_count                int32    actual samples observed in the bin
  expected_count           int32    expected samples at 1 Hz (= bin_minutes * 60)
  completeness             float32  row_count / expected_count, capped at 1.0
  mean_ingest_latency_s    float32  mean ingestLatency converted from ms → s (null if absent)
  mean_processing_delay_s  float32  mean processingDelay converted from ms → s (null if absent)
  restart_count            int32    gaps the stream resumed from inside this bin
  max_gap_s                float32  longest of those gaps in seconds (null if none)

The gap threshold used is recorded in the table's schema metadata under
``gap_seconds``, so a reader can label counts with the threshold that actually
produced them rather than assuming the current default.

Gaps and restarts
-----------------
A **gap** is an interval between consecutive samples longer than
:data:`_GAP_SECONDS`.  A **restart** is the stream resuming after one, so
restarts = gaps, and **continuous blocks = restarts + 1**.

The threshold is 2 s rather than "any missing sample" on purpose.  At 1 Hz a
single dropped epoch produces a 2.000 s interval and is ordinary — measured
across a sample of real station-days, ~0.4% of all intervals are exactly one
dropped sample, which works out to a mean of ~274 of them per station-day.
Counting those as outages would both swamp the signal and duplicate what
``completeness`` already reports.  A strict ``>`` on 2.0 s excludes them and
keeps intervals of two or more consecutive missing epochs, which run ~19 per
station-day.

Each gap is attributed to the bin holding the sample that **resumed** the
stream, not the one where it stopped.  A multi-bin outage is then counted once,
in the bin where data came back, and the bins it spans show up as empty in
``completeness`` — which is what they are.  It also means restart counts sum
correctly when bins are aggregated into coarser ones.

Because a completeness file only sees its own source file (one UTC day), an
outage spanning midnight is invisible to both days' interior intervals: the
first day just ends early and the second just starts late.  ``window_start_ms``
closes that hole — pass the start of the file's intended time window and a
late-starting file counts one restart at its first sample.

Example
-------
  from earthscope_positions.completeness import generate_completeness_file
  generate_completeness_file(Path("data/arrow/WORG.PW.LY_.00/202601/WORG...arrow"))
"""
from __future__ import annotations

import datetime as dt
import io
import pathlib
import re

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.ipc

_BIN_MINUTES = 15
_SAMPLING_HZ = 1.0
_COMPLETENESS_SUFFIX = ".completeness.arrow"

#: An interval between consecutive samples longer than this is a gap, and the
#: sample that ends it is a restart.  See the module docstring for why it is not
#: "any missing sample".  Strict ``>``, so at 1 Hz a lone dropped epoch (a
#: 2.000 s interval) is not a gap but two consecutive missing epochs are.
_GAP_SECONDS = 2.0

#: Columns added after the first release of this format.  A completeness file
#: without them predates gap tracking and is regenerated rather than read with
#: the restart metric silently missing -- see :func:`is_stale`.
_REQUIRED_COLUMNS = ("restart_count", "max_gap_s")

#: Schema-metadata key recording the threshold a file was built with, so a
#: reader can label its counts honestly instead of assuming the current default.
_GAP_SECONDS_META_KEY = b"gap_seconds"


# ---------------------------------------------------------------------------
# Arrow I/O helpers
# ---------------------------------------------------------------------------

def _read_arrow(path: pathlib.Path) -> pa.Table:
    data = path.read_bytes()
    buf = io.BytesIO(data)
    try:
        return pyarrow.ipc.open_file(buf).read_all()
    except pa.ArrowInvalid:
        pass
    buf.seek(0)
    try:
        return pyarrow.ipc.open_stream(buf).read_all()
    except pa.ArrowInvalid:
        raise ValueError(f"Not a valid Arrow IPC file or stream: {path}")


def _write_stream(table: pa.Table, path: pathlib.Path) -> None:
    sink = pa.BufferOutputStream()
    with pyarrow.ipc.new_stream(sink, table.schema) as writer:
        writer.write_table(table)
    path.write_bytes(sink.getvalue().to_pybytes())


def _empty_completeness_table(gap_seconds: float = _GAP_SECONDS) -> pa.Table:
    return _tag_gap_seconds(
        pa.table(
            {
                "bucket_start_ms": pa.array([], type=pa.int64()),
                "row_count": pa.array([], type=pa.int32()),
                "expected_count": pa.array([], type=pa.int32()),
                "completeness": pa.array([], type=pa.float32()),
                "mean_ingest_latency_s": pa.array([], type=pa.float32()),
                "mean_processing_delay_s": pa.array([], type=pa.float32()),
                "restart_count": pa.array([], type=pa.int32()),
                "max_gap_s": pa.array([], type=pa.float32()),
            }
        ),
        gap_seconds,
    )


def _tag_gap_seconds(table: pa.Table, gap_seconds: float) -> pa.Table:
    """Stamp the gap threshold into the table's schema metadata."""
    meta = dict(table.schema.metadata or {})
    meta[_GAP_SECONDS_META_KEY] = str(gap_seconds).encode()
    return table.replace_schema_metadata(meta)


def read_gap_seconds(table: pa.Table) -> "float | None":
    """The gap threshold a completeness table was built with, if it recorded one.

    ``None`` for a file written before gap tracking existed, which is how a
    reader tells "no restarts here" apart from "this file cannot say".
    """
    raw = (table.schema.metadata or {}).get(_GAP_SECONDS_META_KEY)
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Gaps, restarts and continuous blocks
# ---------------------------------------------------------------------------

def find_gaps(
    times_ms: list[int],
    gap_seconds: float = _GAP_SECONDS,
    window_start_ms: "int | None" = None,
) -> list[tuple[int, int]]:
    """Gaps in an ascending list of epoch-ms sample times.

    Returns ``(gap_start_ms, gap_end_ms)`` pairs, where ``gap_end_ms`` is the
    sample that resumed the stream — the restart.  A gap is an interval
    strictly longer than *gap_seconds*; see the module docstring for why that
    is 2 s and not "any missing sample".

    ``window_start_ms`` adds the leading gap from the start of the file's
    intended window to its first sample, which is the only way an outage
    spanning a file boundary is visible at all.

    Shared with the File Explorer's per-file summary so both views count the
    same thing.
    """
    gap_ms = int(round(gap_seconds * 1000))
    gaps: list[tuple[int, int]] = []
    if not times_ms:
        return gaps
    if window_start_ms is not None and times_ms[0] - window_start_ms > gap_ms:
        gaps.append((window_start_ms, times_ms[0]))
    for prev, cur in zip(times_ms, times_ms[1:]):
        if cur - prev > gap_ms:
            gaps.append((prev, cur))
    return gaps


def continuous_blocks(
    times_ms: list[int],
    gap_seconds: float = _GAP_SECONDS,
) -> list[tuple[int, int, int]]:
    """Split sample times into uninterrupted runs.

    Returns ``(start_ms, end_ms, sample_count)`` per block.  The count of these
    is what the File Explorer shows as "continuous blocks"; restarts are one
    fewer.  ``window_start_ms`` is deliberately not accepted here: a late start
    is a restart relative to the expected window, but it does not split the
    samples that are present into two blocks.
    """
    if not times_ms:
        return []
    gap_ms = int(round(gap_seconds * 1000))
    blocks: list[tuple[int, int, int]] = []
    block_start = times_ms[0]
    count = 1
    prev = times_ms[0]
    for cur in times_ms[1:]:
        if cur - prev > gap_ms:
            blocks.append((block_start, prev, count))
            block_start = cur
            count = 0
        count += 1
        prev = cur
    blocks.append((block_start, prev, count))
    return blocks


# ---------------------------------------------------------------------------
# Core computation
# ---------------------------------------------------------------------------

def compute_completeness(
    table: pa.Table,
    sampling_hz: float = _SAMPLING_HZ,
    bin_minutes: int = _BIN_MINUTES,
    gap_seconds: float = _GAP_SECONDS,
    window_start_ms: "int | None" = None,
) -> pa.Table:
    """Compute per-bin completeness, latency and restart stats from a position table.

    The source table must have a ``time`` column containing int64 epoch-milliseconds.
    ``ingestLatency`` and ``processingDelay`` (both int64 ms) are used when present.

    ``window_start_ms`` is the start of the time window the source file was
    meant to cover.  Passing it lets a file that starts late count one restart
    at its first sample, which is the only way an outage that spans a file
    boundary registers anywhere — see the module docstring.
    """
    BIN_MS = bin_minutes * 60 * 1000
    EXPECTED = int(bin_minutes * 60 * sampling_hz)
    schema_names = set(table.schema.names)

    if "time" not in schema_names:
        raise ValueError(f"No 'time' column in table. Columns: {list(schema_names)}")

    times = table.column("time")  # int64 epoch ms

    if len(times) == 0:
        return _empty_completeness_table(gap_seconds)

    min_t: int = pc.min(times).as_py()
    max_t: int = pc.max(times).as_py()

    first_bin = (min_t // BIN_MS) * BIN_MS
    last_bin = (max_t // BIN_MS) * BIN_MS
    n_bins = (last_bin - first_bin) // BIN_MS + 1
    all_bin_starts = [first_bin + i * BIN_MS for i in range(n_bins)]

    # Assign each row to a bin index (int32)
    bin_idx = pc.cast(
        pc.floor(pc.divide(pc.subtract(times, first_bin), BIN_MS)),
        pa.int32(),
    )

    # Build a slim working table for the group-by
    cols: dict[str, pa.ChunkedArray | pa.Array] = {"_bin": bin_idx, "time": times}
    if "ingestLatency" in schema_names:
        cols["ingestLatency"] = table.column("ingestLatency")
    if "processingDelay" in schema_names:
        cols["processingDelay"] = table.column("processingDelay")
    work = pa.table(cols)

    # Aggregate: count + mean latencies per bin
    agg: list[tuple[str, str]] = [("time", "count")]
    if "ingestLatency" in schema_names:
        agg.append(("ingestLatency", "mean"))
    if "processingDelay" in schema_names:
        agg.append(("processingDelay", "mean"))

    grouped = work.group_by("_bin").aggregate(agg)

    # Build O(1) lookup dicts from the (potentially sparse) grouped result
    g_bins: list[int] = grouped.column("_bin").to_pylist()
    count_map: dict[int, int] = dict(zip(g_bins, grouped.column("time_count").to_pylist()))

    have_ingest = "ingestLatency" in schema_names
    have_delay = "processingDelay" in schema_names
    ingest_map: dict[int, float | None] = (
        dict(zip(g_bins, grouped.column("ingestLatency_mean").to_pylist()))
        if have_ingest
        else {}
    )
    delay_map: dict[int, float | None] = (
        dict(zip(g_bins, grouped.column("processingDelay_mean").to_pylist()))
        if have_delay
        else {}
    )

    # Build dense output arrays (fill missing bins with zero / null)
    row_counts: list[int] = [count_map.get(i, 0) for i in range(n_bins)]
    completeness_vals: list[float] = [min(1.0, rc / EXPECTED) for rc in row_counts]

    mean_ingest: list[float | None] = []
    mean_delay: list[float | None] = []
    for i in range(n_bins):
        lat = ingest_map.get(i)
        # ingestLatency is stored as int64 ms in the source; convert to seconds
        mean_ingest.append(lat / 1000.0 if lat is not None else None)
        dly = delay_map.get(i)
        mean_delay.append(dly / 1000.0 if dly is not None else None)

    # Gaps are attributed to the bin holding the sample that *resumed* the
    # stream, so a multi-bin outage counts once (in the bin where data came
    # back) and the counts still sum correctly when bins are coarsened.
    restart_counts = [0] * n_bins
    max_gap_ms: list[int | None] = [None] * n_bins
    for gap_start, gap_end in find_gaps(
        times.to_pylist(), gap_seconds, window_start_ms=window_start_ms
    ):
        idx = (gap_end - first_bin) // BIN_MS
        if not 0 <= idx < n_bins:
            continue                      # resumption outside the binned range
        restart_counts[idx] += 1
        duration = gap_end - gap_start
        if max_gap_ms[idx] is None or duration > max_gap_ms[idx]:
            max_gap_ms[idx] = duration

    return _tag_gap_seconds(
        pa.table(
            {
                "bucket_start_ms": pa.array(all_bin_starts, type=pa.int64()),
                "row_count": pa.array(row_counts, type=pa.int32()),
                "expected_count": pa.array([EXPECTED] * n_bins, type=pa.int32()),
                "completeness": pa.array(completeness_vals, type=pa.float32()),
                "mean_ingest_latency_s": pa.array(mean_ingest, type=pa.float32()),
                "mean_processing_delay_s": pa.array(mean_delay, type=pa.float32()),
                "restart_count": pa.array(restart_counts, type=pa.int32()),
                "max_gap_s": pa.array(
                    [None if g is None else g / 1000.0 for g in max_gap_ms],
                    type=pa.float32(),
                ),
            }
        ),
        gap_seconds,
    )


# ---------------------------------------------------------------------------
# File-level helpers
# ---------------------------------------------------------------------------

def completeness_path(arrow_path: pathlib.Path) -> pathlib.Path:
    """Return the expected .completeness.arrow path for a data .arrow file."""
    return arrow_path.parent / (arrow_path.stem + _COMPLETENESS_SUFFIX)


#: Arrow files under the data tree that are *derived*, not position data.  Both
#: live alongside their source, so a plain ``rglob("*.arrow")`` picks them up:
#: completeness files would be summarised recursively, and PPSD files have no
#: ``time`` column at all and used to abort the whole walk with a ValueError.
#: (The webserver's own scan has always excluded both; this keeps the CLI in
#: step with it.)
_DERIVED_MARKERS = (_COMPLETENESS_SUFFIX[1:], "_ppsd")


def is_source_arrow(path: pathlib.Path) -> bool:
    """Is *path* position data rather than something generated from it?"""
    return path.suffix == ".arrow" and not any(
        marker in path.name for marker in _DERIVED_MARKERS
    )


#: Source filenames are ``<geosncl>_<start>_<end>.arrow`` with compact UTC
#: timestamps (see positions_fetch._arrow_path).  Anchored to the end so a
#: station label containing digits and underscores cannot be mistaken for a
#: timestamp.
_WINDOW_RE = re.compile(r"_(\d{8}T\d{6}Z)_(\d{8}T\d{6}Z)$")


def window_start_ms(arrow_path: pathlib.Path) -> "int | None":
    """Start of the time window a source file was fetched for, from its name.

    ``None`` when the name does not carry one — an externally-produced or
    renamed file — in which case the caller simply loses the ability to notice
    a late start, not correctness of anything else.
    """
    m = _WINDOW_RE.search(arrow_path.stem)
    if m is None:
        return None
    try:
        stamp = dt.datetime.strptime(m.group(1), "%Y%m%dT%H%M%SZ").replace(
            tzinfo=dt.timezone.utc
        )
    except ValueError:
        return None
    return int(stamp.timestamp() * 1000)


def is_stale(out_path: pathlib.Path) -> bool:
    """Was *out_path* written by a version that predates gap tracking?

    Completeness files are generated once and never revisited, so without this
    every tree built before restarts existed would keep serving files missing
    the columns and the metric would silently read as zero everywhere.  A file
    that cannot be opened at all is also stale — regenerating is the repair.

    Deliberately does *not* compare the recorded threshold against the current
    default: someone who generated with an explicit ``--gap-seconds`` should not
    have that quietly undone by the next reader running with the default.  The
    threshold each file used travels with it and is surfaced in the UI.
    """
    try:
        with pyarrow.ipc.open_stream(io.BytesIO(out_path.read_bytes())) as reader:
            names = set(reader.schema.names)
    except Exception:
        return True
    return not set(_REQUIRED_COLUMNS).issubset(names)


def generate_completeness_file(
    arrow_path: pathlib.Path,
    overwrite: bool = False,
    sampling_hz: float = _SAMPLING_HZ,
    gap_seconds: float = _GAP_SECONDS,
) -> pathlib.Path | None:
    """Generate a .completeness.arrow file next to the source .arrow file.

    Skips the file if it already exists and is current; ``overwrite`` forces a
    rewrite.  A file predating gap tracking is deleted and rebuilt (see
    :func:`is_stale`).  Returns the output path, or None if skipped.
    """
    if not is_source_arrow(arrow_path):
        return None  # Never process a completeness or PPSD file

    out_path = completeness_path(arrow_path)
    if out_path.exists():
        if is_stale(out_path):
            # Unlink rather than write over it.  A half-written replacement of a
            # file that is *already* wrong would leave a reader with neither the
            # old shape nor the new one; an absent file is unambiguous, and the
            # write below recreates it.
            out_path.unlink(missing_ok=True)
        elif not overwrite:
            return None

    table = _read_arrow(arrow_path)
    comp_table = compute_completeness(
        table,
        sampling_hz=sampling_hz,
        gap_seconds=gap_seconds,
        window_start_ms=window_start_ms(arrow_path),
    )
    _write_stream(comp_table, out_path)
    return out_path


def stale_or_missing(arrow_root: pathlib.Path) -> list[pathlib.Path]:
    """Source files whose completeness file is absent or predates gap tracking.

    Cheap enough to call for a whole tree — the staleness check reads only the
    IPC schema (~0.02 ms/file) — so callers can report "N files need
    precomputing" without doing the work.
    """
    return [
        p for p in sorted(arrow_root.rglob("*.arrow"))
        if is_source_arrow(p)
        and (not (c := completeness_path(p)).exists() or is_stale(c))
    ]


def generate_all(
    arrow_root: pathlib.Path,
    overwrite: bool = False,
    sampling_hz: float = _SAMPLING_HZ,
    gap_seconds: float = _GAP_SECONDS,
) -> list[pathlib.Path]:
    """Walk ``arrow_root`` and generate completeness files for all data .arrow files.

    Returns the list of paths that were written (skips already-existing,
    up-to-date files unless ``overwrite`` is True).
    """
    generated: list[pathlib.Path] = []
    for arrow_path in sorted(arrow_root.rglob("*.arrow")):
        if not is_source_arrow(arrow_path):
            continue
        out = generate_completeness_file(
            arrow_path,
            overwrite=overwrite,
            sampling_hz=sampling_hz,
            gap_seconds=gap_seconds,
        )
        if out:
            generated.append(out)
    return generated

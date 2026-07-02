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

Example
-------
  from earthscope_positions.completeness import generate_completeness_file
  generate_completeness_file(Path("data/arrow/WORG.PW.LY_.00/202601/WORG...arrow"))
"""
from __future__ import annotations

import io
import pathlib

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.ipc

_BIN_MINUTES = 15
_SAMPLING_HZ = 1.0
_COMPLETENESS_SUFFIX = ".completeness.arrow"


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


def _empty_completeness_table() -> pa.Table:
    return pa.table(
        {
            "bucket_start_ms": pa.array([], type=pa.int64()),
            "row_count": pa.array([], type=pa.int32()),
            "expected_count": pa.array([], type=pa.int32()),
            "completeness": pa.array([], type=pa.float32()),
            "mean_ingest_latency_s": pa.array([], type=pa.float32()),
            "mean_processing_delay_s": pa.array([], type=pa.float32()),
        }
    )


# ---------------------------------------------------------------------------
# Core computation
# ---------------------------------------------------------------------------

def compute_completeness(
    table: pa.Table,
    sampling_hz: float = _SAMPLING_HZ,
    bin_minutes: int = _BIN_MINUTES,
) -> pa.Table:
    """Compute per-bin completeness and latency stats from a position Arrow table.

    The source table must have a ``time`` column containing int64 epoch-milliseconds.
    ``ingestLatency`` and ``processingDelay`` (both int64 ms) are used when present.
    """
    BIN_MS = bin_minutes * 60 * 1000
    EXPECTED = int(bin_minutes * 60 * sampling_hz)
    schema_names = set(table.schema.names)

    if "time" not in schema_names:
        raise ValueError(f"No 'time' column in table. Columns: {list(schema_names)}")

    times = table.column("time")  # int64 epoch ms

    if len(times) == 0:
        return _empty_completeness_table()

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

    return pa.table(
        {
            "bucket_start_ms": pa.array(all_bin_starts, type=pa.int64()),
            "row_count": pa.array(row_counts, type=pa.int32()),
            "expected_count": pa.array([EXPECTED] * n_bins, type=pa.int32()),
            "completeness": pa.array(completeness_vals, type=pa.float32()),
            "mean_ingest_latency_s": pa.array(mean_ingest, type=pa.float32()),
            "mean_processing_delay_s": pa.array(mean_delay, type=pa.float32()),
        }
    )


# ---------------------------------------------------------------------------
# File-level helpers
# ---------------------------------------------------------------------------

def completeness_path(arrow_path: pathlib.Path) -> pathlib.Path:
    """Return the expected .completeness.arrow path for a data .arrow file."""
    return arrow_path.parent / (arrow_path.stem + _COMPLETENESS_SUFFIX)


def generate_completeness_file(
    arrow_path: pathlib.Path,
    overwrite: bool = False,
    sampling_hz: float = _SAMPLING_HZ,
) -> pathlib.Path | None:
    """Generate a .completeness.arrow file next to the source .arrow file.

    Skips the file if it already exists and ``overwrite`` is False.
    Returns the output path, or None if skipped.
    """
    if _COMPLETENESS_SUFFIX[1:] in arrow_path.name:
        return None  # Never process a completeness file itself

    out_path = completeness_path(arrow_path)
    if out_path.exists() and not overwrite:
        return None

    table = _read_arrow(arrow_path)
    comp_table = compute_completeness(table, sampling_hz=sampling_hz)
    _write_stream(comp_table, out_path)
    return out_path


def generate_all(
    arrow_root: pathlib.Path,
    overwrite: bool = False,
    sampling_hz: float = _SAMPLING_HZ,
) -> list[pathlib.Path]:
    """Walk ``arrow_root`` and generate completeness files for all data .arrow files.

    Returns the list of paths that were written (skips already-existing files
    unless ``overwrite`` is True).
    """
    generated: list[pathlib.Path] = []
    for arrow_path in sorted(arrow_root.rglob("*.arrow")):
        if _COMPLETENESS_SUFFIX[1:] in arrow_path.name:
            continue
        out = generate_completeness_file(arrow_path, overwrite=overwrite, sampling_hz=sampling_hz)
        if out:
            generated.append(out)
    return generated

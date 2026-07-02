"""
arrow_inspect — display contents of Apache Arrow IPC files.

Auto-detects both IPC file format (.arrow) and IPC stream format (.arrows).

Usage:
    arrow_inspect /tmp/test.arrow
    arrow_inspect data/arrow/ACSB.PB.LY_.40/202601/*.arrow
    arrow_inspect /tmp/test.arrow --rows 20
    arrow_inspect /tmp/test.arrow --schema-only
    arrow_inspect /tmp/test.arrow --stats
"""
from __future__ import annotations

import argparse
import datetime as dt
import io
import pathlib
import sys

import pyarrow as pa
import pyarrow.ipc


def _read(path: pathlib.Path) -> tuple[pa.Table, str]:
    """Return (table, format) where format is 'file' or 'stream'."""
    data = path.read_bytes()
    buf = io.BytesIO(data)
    try:
        table = pyarrow.ipc.open_file(buf).read_all()
        return table, "file"
    except pa.ArrowInvalid:
        pass
    buf.seek(0)
    try:
        table = pyarrow.ipc.open_stream(buf).read_all()
        return table, "stream"
    except pa.ArrowInvalid:
        pass
    sys.exit(f"ERROR: {path.name} is not a valid Arrow file or stream.")


def _fmt_bytes(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def _fmt_value(val, field: pa.Field) -> str:
    """Human-readable cell value; converts epoch-ms timestamps to ISO."""
    if val is None:
        return "—"
    if pa.types.is_integer(field.type) and "time" in field.name.lower():
        try:
            ts = dt.datetime.fromtimestamp(int(val) / 1000, tz=dt.timezone.utc)
            return ts.strftime("%Y-%m-%dT%H:%M:%SZ")
        except Exception:
            pass
    if isinstance(val, float):
        return f"{val:.6g}"
    return str(val)


def _print_schema(table: pa.Table) -> None:
    print("  Schema:")
    for field in table.schema:
        print(f"    {field.name:<20} {field.type}")


def _print_rows(table: pa.Table, n: int) -> None:
    if table.num_rows == 0:
        print("  (no rows)")
        return

    schema = table.schema
    columns = [schema.field(i) for i in range(len(schema))]
    col_names = [f.name for f in columns]

    # Build rows as lists of formatted strings
    limit = min(n, table.num_rows)
    rows = []
    for i in range(limit):
        row = []
        for j, field in enumerate(columns):
            val = table.column(j)[i].as_py()
            row.append(_fmt_value(val, field))
        rows.append(row)

    # Column widths
    widths = [len(name) for name in col_names]
    for row in rows:
        for j, cell in enumerate(row):
            widths[j] = max(widths[j], len(cell))

    header = "  " + "  ".join(name.ljust(widths[j]) for j, name in enumerate(col_names))
    sep    = "  " + "  ".join("-" * w for w in widths)
    print(header)
    print(sep)
    for row in rows:
        print("  " + "  ".join(cell.ljust(widths[j]) for j, cell in enumerate(row)))

    if table.num_rows > n:
        print(f"  … {table.num_rows - n} more rows")


def _print_stats(table: pa.Table) -> None:
    import pyarrow.compute as pc

    print("  Column statistics:")
    schema = table.schema
    for i in range(len(schema)):
        field = schema.field(i)
        col = table.column(i)
        if pa.types.is_floating(field.type) or pa.types.is_integer(field.type):
            try:
                mn = pc.min(col).as_py()
                mx = pc.max(col).as_py()
                mean = pc.mean(col).as_py()
                nulls = col.null_count
                print(f"    {field.name:<20} min={mn:.6g}  max={mx:.6g}  mean={mean:.6g}  nulls={nulls}")
            except Exception:
                print(f"    {field.name:<20} (stats unavailable)")
        else:
            print(f"    {field.name:<20} ({field.type})")


def _inspect(path: pathlib.Path, args: argparse.Namespace) -> None:
    size = path.stat().st_size
    table, fmt = _read(path)

    bar = "─" * 64
    print(f"\n{bar}")
    print(f"  {path.name}")
    print(f"  format: IPC {fmt}  │  rows: {table.num_rows:,}  │  cols: {table.num_columns}  │  size: {_fmt_bytes(size)}")
    print(bar)

    if table.num_rows == 0:
        _print_schema(table)
        print("  (empty — schema only)")
        return

    if args.schema_only:
        _print_schema(table)
        return

    _print_schema(table)

    if not args.stats:
        print(f"\n  First {min(args.rows, table.num_rows)} of {table.num_rows:,} rows:")
        _print_rows(table, args.rows)

    if args.stats:
        print()
        _print_stats(table)


def main() -> None:
    ap = argparse.ArgumentParser(
        prog="inspect",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="""Display contents of Apache Arrow IPC files.

Auto-detects IPC file format (.arrow) and IPC stream format (.arrows).
Timestamps stored as integer milliseconds-since-epoch are shown as ISO 8601.

Examples:
  inspect /tmp/test.arrow
  inspect data/arrow/ACSB.PB.LY_.40/202601/*.arrow --rows 5
  inspect /tmp/test.arrow --schema-only
  inspect /tmp/test.arrow --stats
""",
    )
    ap.add_argument("files", nargs="+", metavar="FILE",
                    help="Arrow file(s) to inspect.")
    ap.add_argument("--rows", type=int, default=10, metavar="N",
                    help="Number of data rows to display (default: 10).")
    ap.add_argument("--schema-only", action="store_true",
                    help="Print schema only, no data rows.")
    ap.add_argument("--stats", action="store_true",
                    help="Print column statistics instead of rows.")

    args = ap.parse_args()

    paths = []
    for f in args.files:
        p = pathlib.Path(f)
        if not p.exists():
            print(f"WARNING: not found: {p}", file=sys.stderr)
            continue
        paths.append(p)

    if not paths:
        sys.exit("No files found.")

    for path in paths:
        _inspect(path, args)

    print()


if __name__ == "__main__":
    main()

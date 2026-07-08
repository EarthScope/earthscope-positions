"""
es-pos — unified EarthScope GNSS positions CLI.

Fans out to all subcommands.  'inspect' is a separate standalone tool.

Usage:
  es-pos stations get datasource --network-name SHAKE:ShakeAlert -o ShakeAlert
  es-pos stations get radial --latitude 37.5 --longitude -122.0 --distance 100 -o bay_area
  es-pos stations filter -i ShakeAlert -o ShakeAlert.clean --facility JPL

  es-pos fetch get -i ShakeAlert.clean --start 2026-01-01 --end 2026-04-01
  es-pos fetch concat data/arrow/P548.CI.LY_.20/202501/*.arrow -o merged.arrow

  es-pos process completeness
  es-pos process completeness --overwrite --data-dir /custom/data/arrow

  es-pos process ppsd
  es-pos process ppsd -i ShakeAlert --start 2026-01-01 --end 2026-01-31

  es-pos test fetch -i ShakeAlert.clean --start 2026-01-01 --total-duration 25200
  es-pos test plot data/positions_diagnose/diagnose_20260701T000000Z.jsonl
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import pathlib
import sys


def _project_root() -> pathlib.Path:
    return pathlib.Path(__file__).parent.parent.parent


def _build_top_parser() -> tuple[
    argparse.ArgumentParser,
    argparse.ArgumentParser,
    argparse.ArgumentParser,
    argparse.ArgumentParser,
    argparse.ArgumentParser,
]:
    ap = argparse.ArgumentParser(
        prog="es-pos",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="""EarthScope GNSS positions toolkit.

Typical workflow:
  1.  es-pos stations get datasource --network-name SHAKE:ShakeAlert -o ShakeAlert
      (or use the Station Builder tab in the web UI)
  2.  es-pos fetch get -i ShakeAlert --start 2026-01-01 --end 2026-04-01
  3.  es-pos process completeness        (speeds up the web UI)
  4.  es-pos webserver                   (open http://localhost:8000)

Subcommands:
  stations   Discover and manage GNSS station lists.
  fetch      Download and manage position data.
  process    Post-process downloaded data.
  export     Export to MiniSEED 3, GeoJSON, or PPSD plots.
  replay     Replay data to a Kafka topic at original ingest timing.
  webserver  Serve the positions web UI and API.
  test       Diagnostic tools for the positions API.

Use 'es-pos <subcommand> --help' for per-command options.
""",
    )
    sub = ap.add_subparsers(dest="group", metavar="SUBCOMMAND")

    sub.add_parser(
        "stations",
        help="Discover and manage GNSS station lists.",
        add_help=False,
    )
    sub.add_parser(
        "fetch",
        help="Download and manage GNSS position data.",
        add_help=False,
    )

    # ── process ──────────────────────────────────────────────────────────────
    process_p = sub.add_parser(
        "process",
        help="Post-process downloaded data.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="""Post-process downloaded Arrow position files.

Subcommands:
  completeness   Generate 15-min completeness and latency summary files.
  ppsd           Pre-compute per-station-day PPSD cache files.

Use 'es-pos process <subcommand> --help' for per-command options.
""",
    )
    process_sub = process_p.add_subparsers(dest="process_cmd", metavar="SUBCOMMAND")

    # ── process ppsd ─────────────────────────────────────────────────────────
    ppsd_proc_p = process_sub.add_parser(
        "ppsd",
        help="Pre-compute per-station-day PPSD cache files for faster web UI generation.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="""Pre-compute PPSD cache files for all downloaded position files.

For every  <stem>.arrow  file under DATA_DIR, writes a sibling sidecar:
  <stem>_ppsd.arrow

Each sidecar stores a sparse histogram (component, period-bin, power-bin, count)
derived from a Hanning-windowed FFT.  The web UI PPSD Generation page uses these
caches so that grouping / re-grouping is nearly instant; without them the FFT is
run on demand per file (much slower on large date ranges).

Already-existing cache files are skipped unless --overwrite is given.

Station selection: use -i/--input (station list) or --all for all indexed stations.
Date range: use --start / --end to restrict which files are processed.

Examples:
  es-pos process ppsd
  es-pos process ppsd --overwrite
  es-pos process ppsd -i ShakeAlert --start 2026-01-01 --end 2026-01-31
  es-pos process ppsd --data-dir /data/archive/arrow
""",
    )
    ppsd_proc_p.add_argument(
        "-i", "--input",
        action="append",
        metavar="LIST",
        dest="input",
        help=(
            "Station list name or file.  May be repeated.  "
            "Resolved as: path, path+.jsonl, data/station-lists/<name>.jsonl.  "
            "Mutually exclusive with --all."
        ),
    )
    ppsd_proc_p.add_argument(
        "--all", action="store_true",
        help="Process all .arrow files under DATA_DIR (default: ./data/arrow).  Mutually exclusive with -i.",
    )
    ppsd_proc_p.add_argument(
        "--data-dir",
        metavar="PATH",
        help="Root of the Arrow data tree (default: ./data/arrow).",
    )
    ppsd_proc_p.add_argument(
        "--start",
        metavar="YYYY-MM-DD",
        help="Only process files on or after this date.",
    )
    ppsd_proc_p.add_argument(
        "--end",
        metavar="YYYY-MM-DD",
        help="Only process files on or before this date.",
    )
    ppsd_proc_p.add_argument(
        "--overwrite",
        action="store_true",
        help="Regenerate cache files even if they already exist.",
    )
    ppsd_proc_p.add_argument(
        "--workers",
        type=int,
        default=None,
        metavar="N",
        help="Number of parallel worker threads (default: number of CPU cores).",
    )
    ppsd_proc_p.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="Suppress per-file progress output.",
    )

    comp_p = process_sub.add_parser(
        "completeness",
        help="Generate .completeness.arrow files for all downloaded position files.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="""Generate 15-minute completeness and latency summary files.

For every  <stem>.arrow  file under DATA_DIR, writes a sibling file:
  <stem>.completeness.arrow

Each completeness file contains 96 rows (one per 15-min bin in a day) with:
  bucket_start_ms          epoch-ms start of the bin
  row_count                observed samples
  expected_count           expected samples at 1 Hz (900)
  completeness             row_count / expected_count, capped at 1.0
  mean_ingest_latency_s    mean ingestLatency in seconds
  mean_processing_delay_s  mean processingDelay in seconds

Already-existing completeness files are skipped unless --overwrite is given.

The web UI ('es-pos webserver') generates completeness files on demand, but
pre-computing them here makes the Completeness & Latency tab load faster.

Examples:
  es-pos process completeness
  es-pos process completeness --overwrite
  es-pos process completeness --data-dir /data/archive/arrow
""",
    )
    comp_p.add_argument(
        "--data-dir",
        metavar="PATH",
        help="Root of the Arrow data tree (default: ./data/arrow).",
    )
    comp_p.add_argument(
        "--overwrite",
        action="store_true",
        help="Regenerate completeness files even if they already exist.",
    )
    comp_p.add_argument(
        "--sampling-hz",
        type=float,
        default=1.0,
        metavar="HZ",
        help="Expected sample rate in Hz used to compute completeness (default: 1.0).",
    )

    # ── webserver ─────────────────────────────────────────────────────────────
    web_p = sub.add_parser(
        "webserver",
        help="Serve the positions web UI and data API.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="""Start the GNSS positions web server.

Serves the Quasar SPA (from spa/spaBuild/) and the FastAPI data backend
on a single port.  Open http://localhost:8000 in your browser.

Web UI tabs:
  Completeness & Latency
    Heat-map of per-station data completeness and ingest latency.
    Completeness files are generated on-demand (or pre-compute with
    'es-pos process completeness' for faster load times).
    Includes a Fetch button to download missing data.

  Positions
    Interactive ENU time-series plots with linear-axis power spectra
    (down to 5-minute noise).  Select a station list and date range,
    overlay multiple stations.

  Station Builder
    Interactive map of all stations from reference/coordinates/coordinates.csv.
    Click or rectangle-drag to select stations; filter by processing center
    and PPP solution type; save selections as station lists for use with
    'es-pos fetch get'.

  File Plots
    Browse and display PNG/JPEG plots from ./data/plots/, including PPSD
    images generated by 'es-pos export ppsd'.

Examples:
  es-pos webserver
  es-pos webserver --port 9000
  es-pos webserver --data-dir /archive/data/arrow
""",
    )
    web_p.add_argument(
        "--host",
        default="127.0.0.1",
        metavar="HOST",
        help="Bind host (default: 127.0.0.1).",
    )
    web_p.add_argument(
        "--port",
        type=int,
        default=8000,
        metavar="PORT",
        help="Bind port (default: 8000).",
    )
    web_p.add_argument(
        "--data-dir",
        metavar="PATH",
        help="Arrow data root (default: ./data/arrow).",
    )

    # ── test ─────────────────────────────────────────────────────────────────
    test_p = sub.add_parser(
        "test",
        help="Diagnostic tools for the positions API.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="""Diagnostic tools for the EarthScope positions API.

WARNING: 'es-pos test fetch' contacts api.earthscope.org directly.
         It will only return valid auth-endpoint results when connected
         to the EarthScope VPN.  The open endpoint is always reachable.

Subcommands:
  fetch   Concurrency sweep against both positions API endpoints.
  plot    Plot results from a previous 'test fetch' run.

Use 'es-pos test <subcommand> --help' for per-command options.
""",
    )
    test_sub = test_p.add_subparsers(dest="test_cmd", metavar="SUBCOMMAND")
    test_sub.add_parser(
        "fetch",
        help="Concurrency sweep against both positions API endpoints.  Requires EarthScope VPN.",
        add_help=False,
    )
    test_sub.add_parser(
        "plot",
        help="Plot results from a 'test fetch' JSONL file.",
        add_help=False,
    )
    # ── export ────────────────────────────────────────────────────────────────
    export_p = sub.add_parser(
        "export",
        help="Export position data to other formats.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="""Export GNSS position data to other formats.

Subcommands:
  miniseed   Write Arrow files as MiniSEED 3 (8 channels per station-day).
  geojson    Write Arrow files as GeoJSON (compact NDJSON or full FeatureCollection).
  ppsd       Compute Probabilistic Power Spectral Density plots (PNG).

Use 'es-pos export <subcommand> --help' for per-command options.
""",
    )
    export_sub = export_p.add_subparsers(dest="export_cmd", metavar="SUBCOMMAND")

    # ── export geojson ───────────────────────────────────────────────────────
    gj_p = export_sub.add_parser(
        "geojson",
        help="Write Arrow files as GeoJSON.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="""Write GNSS position Arrow files as GeoJSON.

Two output formats (both use ENU — East, North, Up — coordinate order):

  compact   Newline-delimited JSON (NDJSON) — one line per sample:
              {"time":...,"Q":...,"type":"ENU","SNCL":"...",
               "coor":[E,N,U],"err":[Eerr,Nerr,Uerr],"rate":1}

  full      GeoJSON FeatureCollection — one file per station-day with all
            samples as Point features:
              {"type":"FeatureCollection",
               "properties":{"sampleRate":1,"SNCL":"..."},
               "features":[{"type":"Feature",
                             "geometry":{"type":"Point","coordinates":[E,N,U]},
                             "properties":{"coordinateType":"ENU","time":...,
                                           "EError":...,"NError":...,"UError":...,
                                           "quality":...}}, ...]}

Station selection: use -i/--input (station list) or --all for all indexed stations.
Date range: specify exactly two of --start-time, --stop-time, --duration; the
third is derived automatically.

Duration format: '7d' (days), '24h' (hours), '90m' (minutes), '3600s' (seconds),
or a bare integer treated as days.

Examples:
  es-pos export geojson -i ShakeAlert --start-time 2026-01-01 --stop-time 2026-01-31
  es-pos export geojson -i ShakeAlert --start-time 2026-01-01 --duration 30d
  es-pos export geojson --all --stop-time 2026-01-31 --duration 7d
  es-pos export geojson -i ShakeAlert --start-time 2026-01-01 --duration 7d --format compact
""",
    )
    gj_p.add_argument(
        "-i", "--input",
        action="append",
        metavar="LIST",
        dest="input",
        help=(
            "Station list name or file.  May be repeated.  "
            "Resolved in order: as given, with .jsonl, in data/station-lists/, "
            "in data/station-lists/ with .jsonl.  Mutually exclusive with --all."
        ),
    )
    gj_p.add_argument(
        "--all", action="store_true",
        help="Process all stations found in the data directory.  Mutually exclusive with -i.",
    )
    gj_p.add_argument(
        "--data-dir", metavar="PATH",
        help="Arrow data root (default: ./data/arrow).",
    )
    gj_p.add_argument(
        "--start-time", metavar="YYYY-MM-DD",
        help="Start date, inclusive.",
    )
    gj_p.add_argument(
        "--stop-time", metavar="YYYY-MM-DD",
        help="Stop date, inclusive.",
    )
    gj_p.add_argument(
        "--duration", metavar="DURATION",
        help="Duration: '7d', '24h', '90m', '3600s', or bare integer (days).",
    )
    gj_p.add_argument(
        "--format", metavar="FORMAT", default="both",
        choices=["compact", "full", "both"],
        help="Output format: compact, full, or both (default: both).",
    )
    gj_p.add_argument(
        "--spec", metavar="TOML",
        help="Path spec TOML file (default: ./geojson_path_spec.toml).",
    )
    gj_p.add_argument(
        "--root", metavar="PATH",
        help="Override the output root directory from the spec (applied to both formats).",
    )
    gj_p.add_argument(
        "--quiet", "-q", action="store_true",
        help="Suppress per-file progress output.",
    )
    gj_p.add_argument(
        "--force", action="store_true",
        help="Re-convert files even if output already exists.",
    )

    ms_p = export_sub.add_parser(
        "miniseed",
        help="Write Arrow files as MiniSEED 3.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="""Write GNSS position Arrow files as MiniSEED 3.

Each input Arrow file produces 8 MiniSEED files (one per channel):
  LYE  East position          float64  metres
  LYN  North position         float64  metres
  LYZ  Up position            float64  metres
  LY1  East uncertainty       float64  metres
  LY2  North uncertainty      float64  metres
  LY3  Up uncertainty         float64  metres
  LYQ  Quality channel        int32
  LYL  Ingest latency         int32    milliseconds

Output paths are controlled by the path-spec TOML file.  A default spec is
written to miniseed_path_spec.toml in the working directory on first run.

Data gaps (time jumps or null values) produce separate records within each file.

Station selection: use -i/--input (station list) or --all for all indexed stations.
Date range: specify exactly two of --start-time, --stop-time, --duration; the
third is derived automatically.

Duration format: '7d' (days), '24h' (hours), '90m' (minutes), '3600s' (seconds),
or a bare integer treated as days.

Examples:
  es-pos export miniseed -i ShakeAlert --start-time 2026-01-01 --stop-time 2026-01-31
  es-pos export miniseed -i ShakeAlert --start-time 2026-01-01 --duration 30d
  es-pos export miniseed --all --stop-time 2026-01-31 --duration 7d
  es-pos export miniseed -i ShakeAlert --start-time 2026-01-01 --duration 7d --root /archive/mseed
""",
    )
    ms_p.add_argument(
        "-i", "--input",
        action="append",
        metavar="LIST",
        dest="input",
        help=(
            "Station list name or file.  May be repeated.  "
            "Resolved in order: as given, with .jsonl, in data/station-lists/, "
            "in data/station-lists/ with .jsonl.  Mutually exclusive with --all."
        ),
    )
    ms_p.add_argument(
        "--all", action="store_true",
        help="Process all stations found in the data directory.  Mutually exclusive with -i.",
    )
    ms_p.add_argument(
        "--data-dir", metavar="PATH",
        help="Arrow data root (default: ./data/arrow).",
    )
    ms_p.add_argument(
        "--start-time", metavar="YYYY-MM-DD",
        help="Start date, inclusive.",
    )
    ms_p.add_argument(
        "--stop-time", metavar="YYYY-MM-DD",
        help="Stop date, inclusive.",
    )
    ms_p.add_argument(
        "--duration", metavar="DURATION",
        help="Duration: '7d', '24h', '90m', '3600s', or bare integer (days).",
    )
    ms_p.add_argument(
        "--spec", metavar="TOML",
        help="Path spec TOML file (default: ./miniseed_path_spec.toml).",
    )
    ms_p.add_argument(
        "--root", metavar="PATH",
        help="Override the output root directory from the spec.",
    )
    ms_p.add_argument(
        "--quiet", "-q", action="store_true",
        help="Suppress per-file progress output.",
    )
    ms_p.add_argument(
        "--force", action="store_true",
        help="Re-convert files even if output already exists.",
    )

    # ── export ppsd ──────────────────────────────────────────────────────────
    ppsd_p = export_sub.add_parser(
        "ppsd",
        help="Compute Probabilistic Power Spectral Density plots.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="""Compute PPSD (Probabilistic Power Spectral Density) plots.

Each output is a 3-panel PNG (East | North | Up) using a Hanning-windowed,
50%-overlap FFT with parameters matching MonitorApplication.java:
  WINDOW = 1024 samples
  NFFT   = 32768
  X-axis: log10(period)  1 s – 10 000 s
  Y-axis: power dB (m²/Hz)

By default one PNG is produced per station (geosncl).  Use --combined to
accumulate all selected stations into a single plot.

Output directory:
  {output}/{start}_{end}/ppsd-{station}.png

The generated PNG files appear immediately in the File Plots tab of the
web UI ('es-pos webserver') under data/plots/ppsd/.

Examples:
  es-pos export ppsd -i ShakeAlert --start 2026-01-02 --end 2026-01-10
  es-pos export ppsd -i ShakeAlert --start 2026-01-02 --end 2026-01-10 --by-center
  es-pos export ppsd --all --start 2026-01-02 --end 2026-01-10
  es-pos export ppsd data/arrow/P143.CI.LY_.20/202601/*.arrow
  es-pos export ppsd --all --combined --output /archive/plots/ppsd
""",
    )
    ppsd_p.add_argument(
        "files", nargs="*", metavar="ARROW_FILE",
        help="Arrow file(s) to process.  Ignored if -i or --all is given.",
    )
    ppsd_p.add_argument(
        "-i", "--input",
        action="append",
        metavar="LIST",
        dest="input",
        help=(
            "Station list name or file.  May be repeated.  "
            "Resolved in order: as given, with .jsonl, in data/station-lists/, "
            "in data/station-lists/ with .jsonl.  Mutually exclusive with --all."
        ),
    )
    ppsd_p.add_argument(
        "--all", action="store_true",
        help="Process all .arrow files under DATA_DIR (default: ./data/arrow).",
    )
    ppsd_p.add_argument(
        "--data-dir", metavar="PATH",
        help="Arrow data root (default: ./data/arrow).",
    )
    ppsd_p.add_argument(
        "--start", metavar="YYYY-MM-DD",
        help="Only include files on or after this date.",
    )
    ppsd_p.add_argument(
        "--end", metavar="YYYY-MM-DD",
        help="Only include files on or before this date.",
    )
    ppsd_p.add_argument(
        "--by-center", action="store_true",
        help=(
            "Produce one combined plot per processing center (PB, PW, NC, BK, CI) "
            "instead of one plot per stream.  Mutually exclusive with --combined."
        ),
    )
    ppsd_p.add_argument(
        "--combined", action="store_true",
        help="Accumulate all selected stations into one combined plot instead of one per station.",
    )
    ppsd_p.add_argument(
        "--output", metavar="PATH",
        help="Base output directory (default: ./data/plots/ppsd).",
    )
    ppsd_p.add_argument(
        "--quiet", "-q", action="store_true",
        help="Suppress per-file progress output.",
    )

    # ── replay ────────────────────────────────────────────────────────────────
    replay_p = sub.add_parser(
        "replay",
        help="Replay position data to a Kafka topic at original ingest timing.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="""Replay compact GeoJSON position data to a Kafka topic.

Reads Arrow position files and publishes compact NDJSON records so that
each message is sent at the wall-clock time that corresponds to its
original ingest arrival:

    send_time = start_replay_time + (data_arrival - start_data) / time_scale

where data_arrival = data_time + ingest_latency (if --apply-latency).

The message key is the GEOSNCL string.  Connection is plain-text (no TLS).

Station selection: use -i/--input (station list) or --all.
Date range: exactly two of --start-time, --stop-time, --duration.
Duration format: '7d', '24h', '90m', '3600s', or bare integer (days).

The web UI Replay tab provides the same functionality with a progress
chart and one-click curl commands for synchronisation with other jobs.

Examples:
  es-pos replay -i ShakeAlert --start-time 2026-01-01 --stop-time 2026-01-31
  es-pos replay -i ShakeAlert --start-time 2026-01-01 --duration 7d --time-scale 2.0
  es-pos replay --all --start-time 2026-01-01 --duration 1d \\
      --bootstrap-server kafka:9092 --topic my.topic
""",
    )
    replay_p.add_argument(
        "-i", "--input",
        action="append",
        metavar="LIST",
        dest="input",
        help="Station list name or file.  May be repeated.  Mutually exclusive with --all.",
    )
    replay_p.add_argument(
        "--all", action="store_true",
        help="Replay all stations in the data directory.  Mutually exclusive with -i.",
    )
    replay_p.add_argument(
        "--data-dir", metavar="PATH",
        help="Arrow data root (default: ./data/arrow).",
    )
    replay_p.add_argument(
        "--start-time", metavar="YYYY-MM-DD",
        help="Start date, inclusive.",
    )
    replay_p.add_argument(
        "--stop-time", metavar="YYYY-MM-DD",
        help="Stop date, inclusive.",
    )
    replay_p.add_argument(
        "--duration", metavar="DURATION",
        help="Duration: '7d', '24h', '90m', '3600s', or bare integer (days).",
    )
    replay_p.add_argument(
        "--time-scale", type=float, default=1.0, metavar="X",
        help="Replay speed multiplier (default: 1.0 = real-time; 2.0 = 2× faster).",
    )
    replay_p.add_argument(
        "--apply-latency", default=True, action="store_true",
        help="Account for original ingest latency in send timing (default: on).",
    )
    replay_p.add_argument(
        "--no-apply-latency", dest="apply_latency", action="store_false",
        help="Ignore ingest latency; send at data timestamp only.",
    )
    replay_p.add_argument(
        "--bootstrap-server", default="localhost:9092", metavar="HOST:PORT",
        help="Kafka bootstrap server (default: localhost:9092).",
    )
    replay_p.add_argument(
        "--topic",
        default="protected.gnss.positions.shakealert.geojson.compact",
        metavar="TOPIC",
        help="Kafka topic name.",
    )
    replay_p.add_argument(
        "--filter-center", action="append", dest="filter_centers",
        metavar="CENTER", default=[],
        help="Keep only streams with this processing center (PB, PW, NC, BK, CI).  Repeatable.",
    )
    replay_p.add_argument(
        "--filter-solution", action="append", dest="filter_solutions",
        metavar="DIGIT", default=[],
        help="Keep only streams with this PPP solution digit (0-6).  Repeatable.",
    )
    replay_p.add_argument(
        "--filter-type", action="append", dest="filter_types",
        metavar="DIGIT", default=[],
        help="Keep only streams with this solution-type digit (0-3).  Repeatable.",
    )
    replay_p.add_argument(
        "--quiet", "-q", action="store_true",
        help="Suppress progress output.",
    )

    return ap, process_p, web_p, test_p, export_p, replay_p


# ---------------------------------------------------------------------------
# Export helpers: duration, date-range, station-list, arrow-file resolution
# ---------------------------------------------------------------------------

def _parse_duration(s: str) -> dt.timedelta:
    import re
    m = re.fullmatch(r"(\d+(?:\.\d+)?)\s*([dhms]?)", s.strip(), re.IGNORECASE)
    if not m:
        sys.exit(
            f"Invalid duration {s!r}.  "
            "Use '7d' (days), '24h' (hours), '90m' (minutes), '3600s' (seconds), "
            "or a bare integer (treated as days)."
        )
    val, unit = float(m.group(1)), (m.group(2) or "d").lower()
    return {"d": dt.timedelta(days=val), "h": dt.timedelta(hours=val),
            "m": dt.timedelta(minutes=val), "s": dt.timedelta(seconds=val)}[unit]


def _resolve_export_date_range(args: argparse.Namespace) -> tuple[dt.date, dt.date]:
    """Return (start, stop) from exactly two of --start-time / --stop-time / --duration."""
    n_given = sum(x is not None for x in [args.start_time, args.stop_time, args.duration])
    if n_given != 2:
        sys.exit(
            f"Exactly two of --start-time, --stop-time, --duration must be specified "
            f"(got {n_given})."
        )
    start = dt.date.fromisoformat(args.start_time) if args.start_time else None
    stop  = dt.date.fromisoformat(args.stop_time)  if args.stop_time  else None
    dur   = _parse_duration(args.duration) if args.duration else None
    if start and stop:
        return start, stop
    if start and dur:
        return start, (dt.datetime.combine(start, dt.time.min) + dur).date()
    return (dt.datetime.combine(stop, dt.time.min) - dur).date(), stop  # type: ignore[arg-type]


def _resolve_list_path(name: str) -> "pathlib.Path | None":
    """Find a station-list JSONL file — same search order as es-pos fetch."""
    p = pathlib.Path(name)
    stem = p.stem if p.suffix in (".jsonl", ".json") else p.name
    sl = _project_root() / "data" / "station-lists"
    candidates = [
        p,
        p.parent / (stem + ".jsonl"),
        sl / p.name,
        sl / (stem + ".jsonl"),
        sl / (stem + ".json"),           # backward compat
    ]
    return next((c for c in dict.fromkeys(candidates) if c.exists()), None)


def _load_geosncls_from_lists(list_args: list[str]) -> list[str]:
    """Load sorted, deduplicated geosncl strings from one or more station list files."""
    import json as _json
    geosncls: set[str] = set()
    for arg in list_args:
        path = _resolve_list_path(arg)
        if path is None:
            print(f"  [warn] Station list not found: {arg!r}", file=sys.stderr)
            continue
        try:
            raw = path.read_bytes()
            if path.suffix == ".json":
                records = _json.loads(raw)
            else:
                records = [_json.loads(line) for line in raw.splitlines() if line.strip()]
        except Exception as exc:
            print(f"  [warn] Could not read {path}: {exc}", file=sys.stderr)
            continue
        for rec in records:
            gs = rec.get("geosncl") or rec.get("edid", "")
            if gs:
                geosncls.add(gs)
    return sorted(geosncls)


def _resolve_export_arrow_files(
    args: argparse.Namespace,
    start: dt.date,
    stop: dt.date,
) -> list[pathlib.Path]:
    """Return sorted Arrow files for the selected stations within [start, stop]."""
    data_dir = (
        pathlib.Path(args.data_dir)
        if getattr(args, "data_dir", None)
        else _project_root() / "data" / "arrow"
    )
    if not data_dir.exists():
        sys.exit(f"Data directory not found: {data_dir}")

    if args.all and getattr(args, "input", None):
        sys.exit("--all and -i/--input are mutually exclusive.")

    if args.all:
        geosncls = sorted(
            d.name for d in data_dir.iterdir()
            if d.is_dir() and not d.name.startswith(".")
        )
    elif getattr(args, "input", None):
        geosncls = _load_geosncls_from_lists(args.input)
    else:
        geosncls = sorted(
            d.name for d in data_dir.iterdir()
            if d.is_dir() and not d.name.startswith(".")
        )

    if not geosncls:
        sys.exit("No stations found in the specified list(s).")

    arrow_files: list[pathlib.Path] = []
    for geosncl in geosncls:
        gs_dir = data_dir / geosncl
        if not gs_dir.exists():
            continue
        prefix = geosncl + "_"
        for p in sorted(gs_dir.rglob("*.arrow")):
            if ".completeness" in p.name:
                continue
            stem = p.stem
            if not stem.startswith(prefix):
                continue
            rest = stem[len(prefix):]
            # Skip sidecars like _ppsd.arrow: after YYYYMMDD only 'T' is valid
            if len(rest) < 8 or (len(rest) > 8 and rest[8] != "T"):
                continue
            try:
                file_date = dt.date(int(rest[:4]), int(rest[4:6]), int(rest[6:8]))
            except (ValueError, IndexError):
                continue
            if start <= file_date <= stop:
                arrow_files.append(p)

    return arrow_files


def _cmd_export_ppsd(args: argparse.Namespace) -> None:
    import datetime as dt
    from earthscope_positions.export.ppsd_writer import write_ppsd

    data_dir = (
        pathlib.Path(args.data_dir) if args.data_dir
        else _project_root() / "data" / "arrow"
    )

    if args.all:
        if not data_dir.exists():
            sys.exit(f"Data directory not found: {data_dir}")
        arrow_files = sorted(
            p for p in data_dir.rglob("*.arrow")
            if ".completeness" not in p.name
        )
    elif getattr(args, "input", None):
        geosncls = _load_geosncls_from_lists(args.input)
        if not geosncls:
            sys.exit("No geosncls found in the specified station list(s).")
        arrow_files = sorted(
            p
            for gs in geosncls
            for p in (data_dir / gs).rglob("*.arrow")
            if ".completeness" not in p.name
        )
    else:
        arrow_files = [pathlib.Path(f) for f in args.files]

    if not arrow_files:
        sys.exit("No Arrow files found. Use -i <list>, --all, or provide file arguments.")

    start = dt.date.fromisoformat(args.start) if args.start else None
    end   = dt.date.fromisoformat(args.end)   if args.end   else None

    output = (
        pathlib.Path(args.output) if args.output
        else _project_root() / "data" / "plots" / "ppsd"
    )

    by_center = getattr(args, "by_center", False)

    if by_center:
        # Group files by processing center (second dot-segment of their geosncl directory)
        from collections import defaultdict
        center_files: dict[str, list[pathlib.Path]] = defaultdict(list)
        for p in arrow_files:
            geosncl = p.parent.parent.name
            center = geosncl.split(".")[1] if "." in geosncl else "unknown"
            center_files[center].append(p)
        written = []
        for center, files in sorted(center_files.items()):
            w = write_ppsd(files, output, start=start, end=end,
                           separate=False, verbose=not args.quiet,
                           group_label=center)
            written.extend(w)
    else:
        written = write_ppsd(
            arrow_files, output, start=start, end=end,
            separate=not args.combined, verbose=not args.quiet,
        )
    print(f"\nDone.  {len(written)} PPSD plot(s) written.", file=sys.stderr)


def _cmd_export_geojson(args: argparse.Namespace) -> None:
    from earthscope_positions.export.geojson_writer import (
        load_spec, write_arrow_to_geojson, expected_out_paths as gj_expected_paths,
    )

    start, stop = _resolve_export_date_range(args)
    arrow_files = _resolve_export_arrow_files(args, start, stop)

    if not arrow_files:
        sys.exit(
            f"No Arrow files found for the selected stations in range "
            f"{start} – {stop}."
        )

    spec_path = pathlib.Path(args.spec) if args.spec else pathlib.Path("geojson_path_spec.toml")
    if not spec_path.exists():
        default_src = _project_root() / "geojson_path_spec.toml"
        if default_src.exists():
            import shutil
            shutil.copy(default_src, spec_path)
            print(f"Created default path spec: {spec_path}", file=sys.stderr)
        else:
            print(f"[warn] Spec file not found: {spec_path} — using built-in defaults",
                  file=sys.stderr)
            spec_path = None  # type: ignore[assignment]

    spec = load_spec(spec_path)
    if args.root:
        for section in ("compact", "full"):
            spec[section]["root"] = args.root

    formats: tuple[str, ...]
    if args.format == "both":
        formats = ("compact", "full")
    else:
        formats = (args.format,)

    print(
        f"Exporting {len(arrow_files)} file(s)  [{start} – {stop}]  "
        f"format={args.format}",
        file=sys.stderr,
    )
    total_written = 0
    total_skipped = 0
    for i, af in enumerate(arrow_files, 1):
        if not args.force:
            expected = gj_expected_paths(af, spec, formats)
            if expected and all(p.exists() for p in expected):
                if not args.quiet:
                    print(f"[{i}/{len(arrow_files)}] [skip] {af.name}", file=sys.stderr)
                total_skipped += 1
                continue
        if not args.quiet:
            print(f"[{i}/{len(arrow_files)}] {af}", file=sys.stderr)
        try:
            written = write_arrow_to_geojson(
                af, spec, formats=formats, verbose=not args.quiet
            )
            total_written += len(written)
        except Exception as exc:
            print(f"  [error] {exc}", file=sys.stderr)

    suffix = f", {total_skipped} skipped" if total_skipped else ""
    print(f"\nDone.  {total_written} GeoJSON file(s) written{suffix}.", file=sys.stderr)


def _cmd_export_miniseed(args: argparse.Namespace) -> None:
    from earthscope_positions.export.miniseed_writer import (
        load_spec, write_arrow_to_miniseed, expected_out_paths as ms_expected_paths,
    )

    start, stop = _resolve_export_date_range(args)
    arrow_files = _resolve_export_arrow_files(args, start, stop)

    if not arrow_files:
        sys.exit(
            f"No Arrow files found for the selected stations in range "
            f"{start} – {stop}."
        )

    spec_path = pathlib.Path(args.spec) if args.spec else pathlib.Path("miniseed_path_spec.toml")
    if not spec_path.exists():
        default_src = _project_root() / "miniseed_path_spec.toml"
        if default_src.exists():
            import shutil
            shutil.copy(default_src, spec_path)
            print(f"Created default path spec: {spec_path}", file=sys.stderr)
        else:
            print(f"[warn] Spec file not found: {spec_path} — using built-in defaults",
                  file=sys.stderr)
            spec_path = None  # type: ignore[assignment]

    spec = load_spec(spec_path)
    if args.root:
        spec["root"] = args.root

    print(
        f"Exporting {len(arrow_files)} file(s)  [{start} – {stop}]",
        file=sys.stderr,
    )
    total_written = 0
    total_skipped = 0
    for i, af in enumerate(arrow_files, 1):
        if not args.force:
            expected = ms_expected_paths(af, spec)
            if expected and all(p.exists() for p in expected):
                if not args.quiet:
                    print(f"[{i}/{len(arrow_files)}] [skip] {af.name}", file=sys.stderr)
                total_skipped += 1
                continue
        if not args.quiet:
            print(f"[{i}/{len(arrow_files)}] {af}", file=sys.stderr)
        try:
            written = write_arrow_to_miniseed(af, spec, verbose=not args.quiet)
            total_written += len(written)
        except Exception as exc:
            print(f"  [error] {exc}", file=sys.stderr)

    suffix = f", {total_skipped} skipped" if total_skipped else ""
    print(f"\nDone.  {total_written} MiniSEED file(s) written{suffix}.", file=sys.stderr)


def _cmd_webserver(args: argparse.Namespace) -> None:
    import uvicorn
    from earthscope_positions.webserver.webserver import app, set_data_dir

    if args.data_dir:
        set_data_dir(pathlib.Path(args.data_dir))

    print(f"Starting GNSS Positions server → http://{args.host}:{args.port}")
    uvicorn.run(app, host=args.host, port=args.port)


def _cmd_process_completeness(args: argparse.Namespace) -> None:
    from earthscope_positions.process.completeness import generate_all

    data_dir = (
        pathlib.Path(args.data_dir)
        if args.data_dir
        else _project_root() / "data" / "arrow"
    )

    if not data_dir.exists():
        sys.exit(f"Data directory not found: {data_dir}")

    arrow_files = [
        p for p in sorted(data_dir.rglob("*.arrow"))
        if ".completeness" not in p.name
    ]
    if not arrow_files:
        print(f"No .arrow files found under {data_dir}", file=sys.stderr)
        sys.exit(0)

    n_total = len(arrow_files)
    print(
        f"Scanning {n_total} Arrow file(s) under {data_dir} …"
        + (" (overwrite mode)" if args.overwrite else ""),
        file=sys.stderr,
    )

    generated = generate_all(
        data_dir,
        overwrite=args.overwrite,
        sampling_hz=args.sampling_hz,
    )

    skipped = n_total - len(generated)
    print(
        f"Done.  Generated: {len(generated)}  |  Skipped (already exist): {skipped}",
        file=sys.stderr,
    )


def _cmd_process_ppsd(args: argparse.Namespace) -> None:
    import datetime as _dt
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from earthscope_positions.export.ppsd_writer import (
        cache_path_for, compute_ppsd_cache, load_ppsd_cache,
    )

    data_dir = (
        pathlib.Path(args.data_dir) if getattr(args, "data_dir", None)
        else _project_root() / "data" / "arrow"
    )
    if not data_dir.exists():
        sys.exit(f"Data directory not found: {data_dir}")

    if args.all and getattr(args, "input", None):
        sys.exit("--all and -i/--input are mutually exclusive.")

    if args.all:
        geosncls = sorted(
            d.name for d in data_dir.iterdir()
            if d.is_dir() and not d.name.startswith(".")
        )
    elif getattr(args, "input", None):
        geosncls = _load_geosncls_from_lists(args.input)
    else:
        # Default: process everything
        geosncls = sorted(
            d.name for d in data_dir.iterdir()
            if d.is_dir() and not d.name.startswith(".")
        )

    if not geosncls:
        sys.exit("No stations found.")

    start = _dt.date.fromisoformat(args.start) if getattr(args, "start", None) else None
    end   = _dt.date.fromisoformat(args.end)   if getattr(args, "end", None) else None

    # Collect arrow files
    arrow_files: list[pathlib.Path] = []
    for gs in geosncls:
        gs_dir = data_dir / gs
        if not gs_dir.exists():
            continue
        prefix = gs + "_"
        for p in sorted(gs_dir.rglob("*.arrow")):
            if ".completeness" in p.name or "_ppsd" in p.name:
                continue
            stem = p.stem
            if not stem.startswith(prefix):
                continue
            rest = stem[len(prefix):]
            try:
                file_date = _dt.date(int(rest[:4]), int(rest[4:6]), int(rest[6:8]))
            except (ValueError, IndexError):
                continue
            if start and file_date < start:
                continue
            if end and file_date > end:
                continue
            arrow_files.append(p)

    if not arrow_files:
        print("No Arrow files found for the selected stations/date range.", file=sys.stderr)
        sys.exit(0)

    # Separate files that need (re)computation
    todo = [p for p in arrow_files if args.overwrite or not cache_path_for(p).exists()]
    skip = len(arrow_files) - len(todo)
    print(
        f"Found {len(arrow_files)} file(s).  "
        f"To compute: {len(todo)}  |  Already cached: {skip}",
        file=sys.stderr,
    )
    if not todo:
        print("All caches up to date.", file=sys.stderr)
        sys.exit(0)

    n_workers = args.workers or (os.cpu_count() or 4)
    done = 0
    errors = 0

    with ThreadPoolExecutor(max_workers=n_workers, thread_name_prefix="ppsd-cli") as pool:
        futures = {pool.submit(compute_ppsd_cache, p): p for p in todo}
        for fut in as_completed(futures):
            p = futures[fut]
            done += 1
            try:
                fut.result()
                if not args.quiet:
                    print(f"  [{done}/{len(todo)}] {p.name}", file=sys.stderr)
            except Exception as exc:
                errors += 1
                print(f"  [error] {p}: {exc}", file=sys.stderr)

    print(
        f"\nDone.  Computed: {done - errors}  |  Errors: {errors}",
        file=sys.stderr,
    )


def _cmd_replay(args: argparse.Namespace) -> None:
    from earthscope_positions.replay.replay import (
        filter_geosncls, run_cli,
    )

    start, stop = _resolve_export_date_range(args)
    data_dir = (
        pathlib.Path(args.data_dir)
        if getattr(args, "data_dir", None)
        else _project_root() / "data" / "arrow"
    )
    if not data_dir.exists():
        sys.exit(f"Data directory not found: {data_dir}")

    if args.all and getattr(args, "input", None):
        sys.exit("--all and -i/--input are mutually exclusive.")
    if args.all:
        geosncls = sorted(
            d.name for d in data_dir.iterdir()
            if d.is_dir() and not d.name.startswith(".")
        )
    elif getattr(args, "input", None):
        geosncls = _load_geosncls_from_lists(args.input)
    else:
        sys.exit("Specify -i/--input <list> or --all.")

    if not geosncls:
        sys.exit("No stations found in the specified list(s).")

    geosncls = filter_geosncls(
        geosncls,
        args.filter_centers,
        args.filter_solutions,
        args.filter_types,
    )
    if not geosncls:
        sys.exit("No stations remain after applying filters.")

    run_cli(
        geosncls=geosncls,
        start=start,
        stop=stop,
        data_dir=data_dir,
        bootstrap_server=args.bootstrap_server,
        topic=args.topic,
        time_scale=args.time_scale,
        apply_latency=args.apply_latency,
        verbose=not args.quiet,
    )


def main() -> None:
    ap, process_p, web_p, test_p, export_p, replay_p = _build_top_parser()

    if len(sys.argv) == 1:
        ap.print_help()
        sys.exit(0)

    # parse_known_args so we can forward all remaining tokens (including --help)
    # to the delegated module's parser, which gives correct per-command help.
    args, remaining = ap.parse_known_args()

    group = args.group

    if group == "stations":
        sys.argv = ["es-pos stations"] + remaining
        from earthscope_positions.stations.station_list import main as _main
        _main()

    elif group == "fetch":
        sys.argv = ["es-pos fetch"] + remaining
        from earthscope_positions.fetch.positions_fetch import main as _main
        _main()

    elif group == "webserver":
        _cmd_webserver(args)

    elif group == "process":
        process_cmd = getattr(args, "process_cmd", None)
        if process_cmd == "completeness":
            _cmd_process_completeness(args)
        elif process_cmd == "ppsd":
            _cmd_process_ppsd(args)
        else:
            process_p.print_help()
            sys.exit(0)

    elif group == "export":
        export_cmd = getattr(args, "export_cmd", None)
        if export_cmd == "miniseed":
            _cmd_export_miniseed(args)
        elif export_cmd == "geojson":
            _cmd_export_geojson(args)
        elif export_cmd == "ppsd":
            _cmd_export_ppsd(args)
        else:
            export_p.print_help()
            sys.exit(0)

    elif group == "replay":
        _cmd_replay(args)

    elif group == "test":
        test_cmd = getattr(args, "test_cmd", None)
        if test_cmd == "fetch":
            sys.argv = ["es-pos test fetch"] + remaining
            from earthscope_positions.test.positions_diagnose import main as _main
            _main()
        elif test_cmd == "plot":
            sys.argv = ["es-pos test plot"] + remaining
            from earthscope_positions.test.positions_diagnose_plot import main as _main
            _main()
        else:
            test_p.print_help()
            sys.exit(0)

    else:
        ap.print_help()
        sys.exit(0)


if __name__ == "__main__":
    main()

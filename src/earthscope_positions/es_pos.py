"""
es-pos — unified EarthScope GNSS positions CLI.

Fans out to all subcommands.

Usage:
  es-pos lists get-streams --network-name SHAKE:ShakeAlert -o ShakeAlert
  es-pos lists get-radial-streams --latitude 37.5 --longitude -122.0 --distance 100 -o bay_area
  es-pos lists filter-streams -i ShakeAlert -o ShakeAlert.clean --facility JPL

  es-pos fetch --list ShakeAlert.clean --start 2026-01-01 --end 2026-04-01
  es-pos fetch --retry --result error-422

  es-pos process completeness
  es-pos process completeness --overwrite

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

from earthscope_positions import environment, paths


def _project_root() -> pathlib.Path:
    return paths.project_root()


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
  1.  es-pos lists get-streams --network-name SHAKE:ShakeAlert -o ShakeAlert
      (or use the Station/Stream List Builder tabs in the web UI)
  2.  es-pos fetch --list ShakeAlert --start 2026-01-01 --end 2026-04-01
  3.  es-pos process completeness        (speeds up the web UI)
  4.  es-pos webserver                   (open http://localhost:8000)

Subcommands:
  lists      Build and inspect stream lists and station lists.
  fetch      Download and manage position data.
  process    Post-process downloaded data.
  export     Export to MiniSEED (v3 or v2), GeoJSON, or PPSD plots.
  replay     Replay data to a Kafka topic at original ingest timing.
  webserver  Serve the positions web UI and API.
  inspect    Print schema/rows/statistics of Arrow IPC files.
  config     Show or change the persisted data-directory setting.
  test       Diagnostic tools for the positions API.

Use 'es-pos <subcommand> --help' for per-command options.
""",
    )
    sub = ap.add_subparsers(dest="group", metavar="SUBCOMMAND")

    sub.add_parser(
        "lists",
        help="Build and inspect stream lists and station lists.",
        add_help=False,
    )
    # Renamed to `lists` (it manages both stream *and* station lists, which
    # `stations` implied it did not).  Kept only to redirect, not hidden --
    # a plain "invalid choice" would leave the reader guessing.
    sub.add_parser(
        "stations",
        help=argparse.SUPPRESS,
        add_help=False,
    )
    sub.add_parser(
        "fetch",
        help="Download and manage GNSS position data.",
        add_help=False,
    )
    sub.add_parser(
        "inspect",
        help="Print schema, sample rows, and statistics of Arrow IPC files.",
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

Station selection: use -i/--input (stream list) or --all for all indexed stations.
Date range: use --start / --end to restrict which files are processed.

Examples:
  es-pos process ppsd
  es-pos process ppsd --overwrite
  es-pos process ppsd -i ShakeAlert --start 2026-01-01 --end 2026-01-31
""",
    )
    ppsd_proc_p.add_argument(
        "-i", "--input",
        action="append",
        metavar="LIST",
        dest="input",
        help=(
            "Stream list name or file.  May be repeated.  "
            "Resolved as: path, path+.jsonl, data/stream-lists/<name>.jsonl.  "
            "Mutually exclusive with --all."
        ),
    )
    ppsd_proc_p.add_argument(
        "--all", action="store_true",
        help="Process all .arrow files under DATA_DIR (default: ./data/arrow).  Mutually exclusive with -i.",
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
  restart_count            gaps the stream resumed from inside the bin
  max_gap_s                longest of those gaps, in seconds

A gap is an interval between consecutive samples longer than --gap-seconds,
and a restart is the stream coming back from one; continuous blocks are
restarts + 1.  The default of 2 s is chosen so a single dropped epoch (a
2.000 s interval at 1 Hz, and ordinary -- roughly 0.4% of all intervals in real
data) is not counted as an outage; that is what 'completeness' already
measures.  Each gap is attributed to the bin where the data came back, so a
long outage counts once however coarsely the bins are later aggregated.

Already-existing completeness files are skipped unless --overwrite is given --
except files written before restart tracking existed, which are regenerated
regardless, since serving them would make the restart metric read as a uniform
zero.

The threshold each file was built with is stored inside it, so generating with
a non-default --gap-seconds is not silently undone by a later run (or by the
web server) using the default.  The Completeness tab labels its Restarts plot
with the threshold the data actually carries.

The web UI ('es-pos webserver') generates completeness files on demand, but
pre-computing them here makes the Completeness & Latency tab load faster.

Examples:
  es-pos process completeness
  es-pos process completeness --overwrite
  es-pos process completeness --gap-seconds 10 --overwrite
""",
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
    comp_p.add_argument(
        "--gap-seconds",
        type=float,
        default=None,
        metavar="S",
        help="An interval between consecutive samples longer than this counts as "
             "a gap, and the sample ending it as a restart (default: 2). Lower it "
             "to count single dropped samples, raise it to count only sustained "
             "outages. Recorded in each file it writes.",
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
    (down to 5-minute noise).  Select a stream list and date range,
    overlay multiple stations.

  Station Builder
    Interactive map of all stations from the editable coordinates file
    (<data-dir>/coordinates.csv, seeded from resources/coordinates.csv).
    Click or rectangle-drag to select stations; filter by processing center
    and PPP solution type; save selections as stream lists for use with
    'es-pos fetch'.  Update/Edit Coordinates add or change stations.

  File Plots
    Browse and display PNG/JPEG plots from ./data/plots/, including PPSD
    images generated by 'es-pos export ppsd'.

Examples:
  es-pos webserver
  es-pos webserver --port 9000
""",
    )
    web_p.add_argument(
        "--host",
        default="127.0.0.1",
        metavar="HOST",
        help="Bind address (default: 127.0.0.1).  Use 0.0.0.0 to accept remote connections.",
    )
    web_p.add_argument(
        "--port",
        type=int,
        default=8000,
        metavar="PORT",
        help="Bind port (default: 8000).",
    )
    web_p.add_argument(
        "--hostname",
        default="localhost",
        metavar="NAME",
        help=(
            "Externally-reachable hostname used for callback URLs shown in the UI "
            "(e.g. the Replay curl commands).  Default: localhost.  Set this to the "
            "server's public name/IP when running remotely."
        ),
    )

    # ── config ───────────────────────────────────────────────────────────────
    config_p = sub.add_parser(
        "config",
        help="Show or change the persisted data-directory setting.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="""Inspect and change the persisted earthscope-positions settings.

Settings live in a single JSON file in your home directory
(~/.earthscope-positions.json by default; override with ES_POS_CONFIG_FILE).
It is created at runtime and is unaffected by upgrading or reinstalling the
package.

The data directory is resolved in this order — the first that applies wins:

  1. the ES_POS_DATA_DIRECTORY environment variable
  2. data_directory in the config file
  3. first run on a terminal: you are asked, and the answer is saved to (2)
  4. otherwise the default, ~/earthscope-positions

There is no --data-directory flag; the environment variable covers the same
ground for automated callers.  If it is set and disagrees with the configured
value, every command prints a one-time note showing both.

Directories used before are remembered, so you can switch between them by
number instead of retyping a path.

ENVIRONMENT (production or stage)

Each data directory is tied to one EarthScope deployment, recorded in
<data directory>/.config/environment.json:

  prod    api.earthscope.org       (the default; no marker file needed)
  stage   api.dev.earthscope.org   (es profile "stage")

The two issue different EDIDs for the same station, so a directory is only
ever one of them.  The single way to put a directory on stage is:

  es-pos config use-data-dir --stage PATH

and it is refused for a directory that already holds production data — use a
separate directory for stage rather than mixing the two in one Arrow tree.
Every subcommand here reports which environment it is talking about.

Subcommands:
  show             Print the resolved data directory, its environment, and which layer set it.
  list-data-dirs   List remembered data directories with their environments, marking the active one.
  use-data-dir     Switch the active data directory (by number or path); --stage/--prod set its environment.
  set-data-dir     Record a data directory in the config file (does not move data).
  move-data-dir    Move the existing data tree somewhere else, then record it.
  forget-data-dir  Remove a directory from the remembered list (leaves data alone).

Examples:
  es-pos config show
  es-pos config list-data-dirs
  es-pos config use-data-dir 2
  es-pos config use-data-dir --stage ~/earthscope-positions-stage
  es-pos config use-data-dir --prod ~/earthscope-positions
  es-pos config set-data-dir /mnt/gnss/positions
  es-pos config move-data-dir /Volumes/BigDisk/positions
""",
    )
    config_sub = config_p.add_subparsers(dest="config_cmd", metavar="SUBCOMMAND")
    config_sub.add_parser(
        "show",
        help="Print the resolved data directory, its environment, and which layer set it.",
    )
    config_sub.add_parser(
        "list-data-dirs",
        help="List remembered data directories with their environments.",
        description=(
            "List every data directory this install has used, in the order they "
            "were first seen, with the active one marked and each one's "
            "environment (production or stage) shown.  The numbers are stable "
            "and are what 'use-data-dir' and 'forget-data-dir' accept."
        ),
    )
    cfg_use_p = config_sub.add_parser(
        "use-data-dir",
        help="Switch the active data directory; --stage/--prod set its environment.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=(
            "Make a remembered directory active.  TARGET is either a number from\n"
            "'es-pos config list-data-dirs' or a path.  A path that has not been\n"
            "seen before is remembered too.  No data is moved.\n"
            "\n"
            "This is also the only command that can put a directory on the stage\n"
            "deployment (api.dev.earthscope.org):\n"
            "\n"
            "  es-pos config use-data-dir --stage ~/earthscope-positions-stage\n"
            "\n"
            "Without --stage/--prod the directory keeps whatever environment it\n"
            "already has (production for a directory that has never been marked).\n"
            "Changing the environment of a directory that already holds data is\n"
            "refused: prod and stage EDIDs differ, so the two cannot share a tree."
        ),
    )
    cfg_use_p.add_argument(
        "target", metavar="TARGET",
        help="Number from 'list-data-dirs', or a directory path.",
    )
    cfg_use_env = cfg_use_p.add_mutually_exclusive_group()
    cfg_use_env.add_argument(
        "--stage", dest="environment", action="store_const", const="stage",
        help="Point TARGET at the stage deployment (api.dev.earthscope.org, "
             "es profile 'stage').",
    )
    cfg_use_env.add_argument(
        "--prod", "--production", dest="environment",
        action="store_const", const="prod",
        help="Point TARGET back at production (api.earthscope.org). This is the "
             "default for an unmarked directory.",
    )
    cfg_use_p.add_argument(
        "--profile", metavar="NAME",
        help="es profile holding this environment's tokens, recorded with the "
             "directory.  Defaults to 'stage' for --stage and 'default' for "
             "--prod; pass it when your credentials for that deployment already "
             "live under a differently-named profile in ~/.earthscope/config.toml. "
             "Requires --stage or --prod.",
    )
    cfg_use_p.add_argument(
        "--force", action="store_true",
        help="Change the environment even though TARGET already holds data. "
             "Mixes prod and stage EDIDs in one tree — only for a directory you "
             "know is safe to re-point.",
    )
    cfg_forget_p = config_sub.add_parser(
        "forget-data-dir",
        help="Remove a directory from the remembered list (leaves data alone).",
        description=(
            "Drop a directory from the remembered list.  The directory and its "
            "contents are untouched -- this only stops it being offered.  The "
            "active directory cannot be forgotten; switch away from it first."
        ),
    )
    cfg_forget_p.add_argument(
        "target", metavar="TARGET",
        help="Number from 'list-data-dirs', or a directory path.",
    )
    cfg_set_p = config_sub.add_parser(
        "set-data-dir",
        help="Record a data directory in the config file (does not move data).",
        description=(
            "Record PATH as the data directory.  This only changes where "
            "earthscope-positions looks; it does not move any existing data.  "
            "Use 'es-pos config move-data-dir' for that."
        ),
    )
    cfg_set_p.add_argument("path", metavar="PATH", help="Directory to record.")
    cfg_set_p.add_argument(
        "--no-create", action="store_true",
        help="Do not create the directory if it does not exist.",
    )
    cfg_move_p = config_sub.add_parser(
        "move-data-dir",
        help="Move the existing data tree to PATH, then record it.",
        description=(
            "Move the current data directory to PATH and record the new location.  "
            "PATH must not already exist, or must be empty.  Refuses to move a "
            "directory into itself.  The move is a real relocation, so it can take "
            "a while for a large tree."
        ),
    )
    cfg_move_p.add_argument("path", metavar="PATH", help="New location for the data directory.")
    cfg_move_p.add_argument(
        "--yes", "-y", action="store_true",
        help="Skip the confirmation prompt.",
    )

    # ── test ─────────────────────────────────────────────────────────────────
    test_p = sub.add_parser(
        "test",
        help="Diagnostic tools for the positions API.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="""Diagnostic tools for the EarthScope positions API.

Both endpoints follow the active data directory's environment (production or
stage) -- see 'es-pos config show'.

WARNING: 'es-pos test fetch' contacts the positions API directly
         (api.earthscope.org on production).  It will only return valid
         auth-endpoint results when connected to the EarthScope VPN.
         Production's open endpoint is always reachable; stage has none, so a
         stage run sweeps the authenticated endpoint alone.

Subcommands:
  fetch   Concurrency sweep against the positions API endpoints.
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
  geojson    Write Arrow files as GeoJSON JSONL (compact or full Feature per line).
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

Two output formats, both written as JSONL (one JSON object per line) and both
using ENU — East, North, Up — coordinate order:

  compact   *.compact.geojson.jsonl — one compact record per sample:
              {"time":...,"Q":...,"type":"ENU","SNCL":"...",
               "coor":[E,N,U],"err":[Eerr,Nerr,Uerr],"rate":1}

  full      *.full.geojson.jsonl — one GeoJSON Feature per sample:
              {"type":"Feature",
               "geometry":{"type":"Point","coordinates":[E,N,U]},
               "properties":{"coordinateType":"ENU","SNCL":"...","time":...,
                             "EError":...,"NError":...,"UError":...,
                             "quality":...,"sampleRate":1}}

Station selection: use -i/--input (stream list) or --all for all indexed stations.
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
            "Stream list name or file.  May be repeated.  "
            "Resolved in order: as given, with .jsonl, in data/stream-lists/, "
            "in data/stream-lists/ with .jsonl.  Mutually exclusive with --all."
        ),
    )
    gj_p.add_argument(
        "--all", action="store_true",
        help="Process all stations found in the data directory.  Mutually exclusive with -i.",
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
        help="Path spec TOML file (default: <data-directory>/resources/geojson_path_spec.toml).",
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
        help="Write Arrow files as MiniSEED (version 3 by default, 2 optional).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="""Write GNSS position Arrow files as MiniSEED.

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
written to <data-directory>/resources/miniseed_path_spec.toml on first run.

Format version defaults to 3 (the current FDSN standard).  Pass
--format-version 2 for classic SEED, for tooling that cannot read version 3;
version 2 requires the spec's max_record_length to be a power of two.

Data gaps (time jumps or null values) produce separate records within each file.

Station selection: use -i/--input (stream list) or --all for all indexed stations.
Date range: specify exactly two of --start-time, --stop-time, --duration; the
third is derived automatically.

Duration format: '7d' (days), '24h' (hours), '90m' (minutes), '3600s' (seconds),
or a bare integer treated as days.

Examples:
  es-pos export miniseed -i ShakeAlert --start-time 2026-01-01 --stop-time 2026-01-31
  es-pos export miniseed -i ShakeAlert --start-time 2026-01-01 --duration 30d
  es-pos export miniseed --all --stop-time 2026-01-31 --duration 7d
  es-pos export miniseed -i ShakeAlert --start-time 2026-01-01 --duration 7d --root /archive/mseed
  es-pos export miniseed -i ShakeAlert --start-time 2026-01-01 --duration 7d --format-version 2
""",
    )
    ms_p.add_argument(
        "-i", "--input",
        action="append",
        metavar="LIST",
        dest="input",
        help=(
            "Stream list name or file.  May be repeated.  "
            "Resolved in order: as given, with .jsonl, in data/stream-lists/, "
            "in data/stream-lists/ with .jsonl.  Mutually exclusive with --all."
        ),
    )
    ms_p.add_argument(
        "--all", action="store_true",
        help="Process all stations found in the data directory.  Mutually exclusive with -i.",
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
        help="Path spec TOML file (default: <data-directory>/resources/miniseed_path_spec.toml).",
    )
    ms_p.add_argument(
        "--root", metavar="PATH",
        help="Override the output root directory from the spec.",
    )
    ms_p.add_argument(
        "--format-version", type=int, choices=(2, 3), default=None,
        help=(
            "MiniSEED format version to write (default: the spec's "
            "[encoding] format_version, which ships as 3)."
        ),
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
  {output}/{mode}/ppsd-{name}/ppsd-{name}_{start}_{end}.png
  (mode: by-stream, by-center, or all)

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
            "Stream list name or file.  May be repeated.  "
            "Resolved in order: as given, with .jsonl, in data/stream-lists/, "
            "in data/stream-lists/ with .jsonl.  Mutually exclusive with --all."
        ),
    )
    ppsd_p.add_argument(
        "--all", action="store_true",
        help="Process all .arrow files under DATA_DIR (default: ./data/arrow).",
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

Station selection: use -i/--input (stream list) or --all.
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
        help="Stream list name or file.  May be repeated.  Mutually exclusive with --all.",
    )
    replay_p.add_argument(
        "--all", action="store_true",
        help="Replay all stations in the data directory.  Mutually exclusive with -i.",
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

    return ap, process_p, web_p, test_p, export_p, replay_p, config_p


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
    sl = paths.stream_lists_dir()
    candidates = [
        p,
        p.parent / (stem + ".jsonl"),
        sl / p.name,
        sl / (stem + ".jsonl"),
        sl / (stem + ".json"),           # backward compat
    ]
    return next((c for c in dict.fromkeys(candidates) if c.exists()), None)


def _load_geosncls_from_lists(list_args: list[str]) -> list[str]:
    """Load sorted, deduplicated geosncl strings from one or more stream list files."""
    import json as _json
    geosncls: set[str] = set()
    for arg in list_args:
        path = _resolve_list_path(arg)
        if path is None:
            print(f"  [warn] Stream list not found: {arg!r}", file=sys.stderr)
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
    data_dir = paths.arrow_dir()
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
            # Silently skip sidecar files — they are not position data.
            if ".completeness" in p.name or "_ppsd" in p.name:
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

    data_dir = paths.arrow_dir()

    if args.all:
        if not data_dir.exists():
            sys.exit(f"Data directory not found: {data_dir}")
        arrow_files = sorted(
            p for p in data_dir.rglob("*.arrow")
            if ".completeness" not in p.name and "_ppsd" not in p.name
        )
    elif getattr(args, "input", None):
        geosncls = _load_geosncls_from_lists(args.input)
        if not geosncls:
            sys.exit("No geosncls found in the specified stream list(s).")
        arrow_files = sorted(
            p
            for gs in geosncls
            for p in (data_dir / gs).rglob("*.arrow")
            if ".completeness" not in p.name and "_ppsd" not in p.name
        )
    else:
        arrow_files = [pathlib.Path(f) for f in args.files]

    if not arrow_files:
        sys.exit("No Arrow files found. Use -i <list>, --all, or provide file arguments.")

    start = dt.date.fromisoformat(args.start) if args.start else None
    end   = dt.date.fromisoformat(args.end)   if args.end   else None

    output = (
        pathlib.Path(args.output) if args.output
        else paths.plots_dir() / "ppsd"
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

    spec_path = pathlib.Path(args.spec) if args.spec else paths.geojson_spec_file()
    if not spec_path.exists():
        default_src = paths.bundled_resources_dir() / "geojson_path_spec.toml"
        if default_src.exists():
            import shutil
            spec_path.parent.mkdir(parents=True, exist_ok=True)
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
        DEFAULT_FORMAT_VERSION, load_spec, write_arrow_to_miniseed,
        expected_out_paths as ms_expected_paths,
    )

    start, stop = _resolve_export_date_range(args)
    arrow_files = _resolve_export_arrow_files(args, start, stop)

    if not arrow_files:
        sys.exit(
            f"No Arrow files found for the selected stations in range "
            f"{start} – {stop}."
        )

    spec_path = pathlib.Path(args.spec) if args.spec else paths.miniseed_spec_file()
    if not spec_path.exists():
        default_src = paths.bundled_resources_dir() / "miniseed_path_spec.toml"
        if default_src.exists():
            import shutil
            spec_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(default_src, spec_path)
            print(f"Created default path spec: {spec_path}", file=sys.stderr)
        else:
            print(f"[warn] Spec file not found: {spec_path} — using built-in defaults",
                  file=sys.stderr)
            spec_path = None  # type: ignore[assignment]

    spec = load_spec(spec_path)
    if args.root:
        spec["root"] = args.root

    version = (
        args.format_version
        if args.format_version is not None
        else int(spec["encoding"].get("format_version", DEFAULT_FORMAT_VERSION))
    )

    print(
        f"Exporting {len(arrow_files)} file(s) as MiniSEED {version}  [{start} – {stop}]",
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
            written = write_arrow_to_miniseed(
                af, spec, format_version=version, verbose=not args.quiet,
            )
            total_written += len(written)
        except Exception as exc:
            print(f"  [error] {exc}", file=sys.stderr)

    suffix = f", {total_skipped} skipped" if total_skipped else ""
    print(f"\nDone.  {total_written} MiniSEED {version} file(s) written{suffix}.",
          file=sys.stderr)


def _dir_size(path: pathlib.Path) -> tuple[int, int]:
    """(total bytes, file count) under *path*; missing dirs count as empty."""
    total = count = 0
    for f in path.rglob("*"):
        try:
            if f.is_file() and not f.is_symlink():
                total += f.stat().st_size
                count += 1
        except OSError:
            continue
    return total, count


def _fmt_size(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


_SOURCE_LABELS = {
    "env":     f"{paths.ENV_VAR} environment variable",
    "config":  "config file",
    "prompt":  "answered at the first-run prompt (saved to the config file)",
    "default": "built-in default (nothing configured)",
}

_ENV_SOURCE_LABELS = {
    "env":      f"{environment.ENV_VAR} environment variable",
    "data-dir": "the data directory's .config/environment.json",
    "default":  "built-in default (directory not marked)",
}


def _env_tag(env: "environment.Environment") -> str:
    """One-word environment marker for a listing line.

    Production is the ordinary case and gets no decoration; anything else is
    flagged, so a stage directory cannot be skimmed past in a numbered list.
    """
    return "" if env.name == environment.DEFAULT_ENVIRONMENT else f"  [{env.label}]"


def _print_environment_block() -> None:
    """The environment stanza shared by every `es-pos config` subcommand."""
    env = environment.current()
    source = environment.current_source()
    print(f"Environment:     {env.label} ({env.name})")
    print(f"  set by:        {_ENV_SOURCE_LABELS.get(source, source)}")
    print(f"  API:           {env.api_url}")
    print(f"  es profile:    {environment.profile()}")


def _warn_if_profile_undefined() -> None:
    """Say so now if the active environment's es profile is not configured.

    Checked here rather than left to the first API call: a switch is when
    someone can act on it, whereas the failure otherwise surfaces mid-fetch as
    the SDK's bare "Profile 'stage' does not exist".
    """
    defined = environment.configured_profiles()
    if defined is None or environment.profile() in defined:
        return
    print()
    for line in environment.profile_setup_hint().splitlines():
        print(f"[note] {line}" if not line.startswith(" ") else f"       {line}")


def _cmd_config_show(args: argparse.Namespace) -> None:
    resolved = paths.base_dir()
    source = paths.base_dir_source()
    cfg_path = paths.config_path()
    configured = paths.configured_data_dir()

    print(f"Data directory:  {resolved}")
    print(f"  set by:        {_SOURCE_LABELS.get(source, source)}")
    print(f"  exists:        {'yes' if resolved.exists() else 'no (created on first write)'}")
    if resolved.exists():
        size, count = _dir_size(resolved)
        print(f"  contents:      {_fmt_size(size)} in {count:,} file(s)")
    print()
    _print_environment_block()
    marker = environment.marker_path(resolved)
    print(f"  marker file:   {marker}"
          f"{'' if marker.exists() else '  (not written — production)'}")
    if environment.is_default():
        print(f"  to use stage:  es-pos config use-data-dir --stage PATH")
    else:
        _warn_if_profile_undefined()
    print()
    print(f"Config file:     {cfg_path}")
    print(f"  exists:        {'yes' if cfg_path.exists() else 'no'}")
    print(f"  data_directory:{' ' + str(configured) if configured else ' (not set)'}")

    known = paths.known_data_dirs()
    if len(known) > 1:
        print(f"\nRemembered directories ({len(known)}) — switch with "
              f"'es-pos config use-data-dir N':")
        _print_known(known, resolved)

    env = os.environ.get(paths.ENV_VAR)
    if env:
        print(f"\n{paths.ENV_VAR}={env}")
    if configured is not None and configured != resolved:
        print(
            f"\nNote: the active directory differs from the configured one.\n"
            f"  To make the config match what is in use:  es-pos config set-data-dir {resolved}\n"
            f"  To use the configured location instead:   unset the override above."
        )


def _print_known(known: list[pathlib.Path], active: pathlib.Path) -> None:
    """Numbered listing of remembered directories, with their environments.

    Numbers come from the config file's stored order, which is stable, so a
    number a user reads here is still valid after switching.
    """
    for i, path in enumerate(known, 1):
        mark = "*" if path == active else " "
        if not path.exists():
            state = "  (missing)"
        else:
            size, count = _dir_size(path)
            state = f"  ({_fmt_size(size)}, {count:,} file(s))"
        try:
            tag = _env_tag(environment.environment_of(path))
        except ValueError as exc:
            # An unrecognised marker (written by a newer version): say so rather
            # than showing the directory as production, which it is not.
            tag = f"  [unknown environment: {exc}]"
        print(f"  {mark} {i}. {path}{state}{tag}")


def _resolve_known_target(target: str) -> pathlib.Path:
    """Turn a listing number or a path into a directory.

    Numbers are resolved against the remembered list; anything else is treated
    as a path, so a directory that has never been used still works.
    """
    known = paths.known_data_dirs()
    if target.isdigit():
        index = int(target)
        if not 1 <= index <= len(known):
            sys.exit(
                f"No remembered data directory numbered {index}.  "
                f"There {'is' if len(known) == 1 else 'are'} {len(known)}.  "
                f"Run 'es-pos config list-data-dirs' to see them."
            )
        return known[index - 1]
    return pathlib.Path(target).expanduser()


def _cmd_config_list_data_dirs(args: argparse.Namespace) -> None:
    known = paths.known_data_dirs()
    if not known:
        print("No data directories remembered yet.")
        print("Set one with: es-pos config set-data-dir PATH")
        return
    active = paths.base_dir()
    print(f"Remembered data directories ({len(known)}), '*' = active:")
    _print_known(known, active)
    print()
    _print_environment_block()
    if paths.base_dir_source() == "env":
        print(f"\n[note] {paths.ENV_VAR} is overriding the active entry "
              f"for this run ({active}).")


def _cmd_config_use_data_dir(args: argparse.Namespace) -> None:
    target = _resolve_known_target(args.target)
    requested = getattr(args, "environment", None)
    if args.profile and requested is None:
        sys.exit(
            "--profile only has meaning alongside --stage or --prod: it is "
            "recorded in the directory's environment marker, and without one of "
            "those there is no marker to write.\n"
            "  For a one-off override use the ES_PROFILE environment variable."
        )

    # The environment is written before the directory becomes active, and the
    # conflict check runs before either: a refusal must leave the previous
    # active directory untouched rather than switching to a directory it then
    # declines to mark.
    if requested is not None:
        resolved_target = pathlib.Path(target).expanduser().resolve()
        conflict = environment.describe_switch_conflict(resolved_target, requested)
        if conflict and not args.force:
            sys.exit(
                f"Refusing to change the environment of a directory that already "
                f"holds data:\n\n{conflict}\n\n"
                f"  Or, if you are sure this tree can be re-pointed, pass --force."
            )
        resolved_target.mkdir(parents=True, exist_ok=True)
        marker = environment.write_marker(
            resolved_target, requested, profile=args.profile
        )
        env_obj = environment.ENVIRONMENTS[requested]
        print(f"Environment for {resolved_target} is now {env_obj.label} ({env_obj.name})")
        print(f"  recorded in {marker}")
        if conflict:
            print("  [warn] --force used: this tree now mixes environments.")

    saved = paths.set_configured_data_dir(target)
    environment.reset_cache()
    print(f"Active data directory is now {saved}")
    print(f"  recorded in {paths.config_path()}")
    if not saved.exists():
        print("  (directory does not exist yet — it is created on first write)")
    print()
    _print_environment_block()
    _warn_if_profile_undefined()
    if not environment.is_default():
        print(f"\n  Log in for this environment with: "
              f"es user login --profile {environment.profile()}")

    env = os.environ.get(paths.ENV_VAR)
    if env and pathlib.Path(env).expanduser() != saved:
        print(
            f"\n[note] {paths.ENV_VAR} is set to {env} and takes precedence over\n"
            f"       the config file.  Unset it for this switch to take effect."
        )
    env_override = os.environ.get(environment.ENV_VAR)
    if env_override and requested is not None and env_override.strip() != requested:
        print(
            f"\n[note] {environment.ENV_VAR} is set to {env_override} and takes\n"
            f"       precedence over the directory's marker.  Unset it for this\n"
            f"       change to take effect."
        )


def _cmd_config_forget_data_dir(args: argparse.Namespace) -> None:
    target = _resolve_known_target(args.target)
    try:
        removed = paths.forget_data_dir(target)
    except ValueError as exc:
        sys.exit(str(exc))
    if not removed:
        sys.exit(f"{target} is not in the remembered list.")
    print(f"Forgot {target}{_env_tag(environment.environment_of(target))}")
    print("  the directory and its contents were not touched.")


def _cmd_config_set_data_dir(args: argparse.Namespace) -> None:
    target = pathlib.Path(args.path).expanduser()
    if not args.no_create:
        target.mkdir(parents=True, exist_ok=True)
    saved = paths.set_configured_data_dir(target)
    environment.reset_cache()
    print(f"Data directory set to {saved}")
    print(f"  recorded in {paths.config_path()}")
    if not saved.exists():
        print("  (directory does not exist yet — it is created on first write)")
    print()
    _print_environment_block()
    if environment.is_default():
        # set-data-dir deliberately has no --stage: putting a directory on
        # stage is a single, deliberate act, and it lives on use-data-dir.
        print("\n  This directory is on production.  To put one on stage:")
        print(f"    es-pos config use-data-dir --stage {saved}")
    # An override still in effect would quietly win over what we just saved.
    env = os.environ.get(paths.ENV_VAR)
    if env and pathlib.Path(env).expanduser() != saved:
        print(
            f"\n[note] {paths.ENV_VAR} is set to {env} and takes precedence over the\n"
            f"       config file.  Unset it for this setting to take effect."
        )


def _cmd_config_move_data_dir(args: argparse.Namespace) -> None:
    import shutil

    src = paths.base_dir().resolve()
    dst = pathlib.Path(args.path).expanduser().resolve()

    if not src.exists():
        sys.exit(f"Current data directory does not exist: {src}\n"
                 f"Nothing to move — use 'es-pos config set-data-dir' instead.")
    if dst == src:
        sys.exit(f"Source and destination are the same directory: {src}")
    if src in dst.parents:
        sys.exit(f"Cannot move {src} into its own subdirectory ({dst}).")
    if dst.exists():
        if not dst.is_dir():
            sys.exit(f"Destination exists and is not a directory: {dst}")
        if any(dst.iterdir()):
            sys.exit(f"Destination already exists and is not empty: {dst}")

    size, count = _dir_size(src)
    print(f"Move data directory")
    print(f"  from: {src}")
    print(f"  to:   {dst}")
    print(f"  size: {_fmt_size(size)} in {count:,} file(s)")
    print(f"  env:  {environment.environment_of(src).label}  (moves with the data)")

    if not args.yes and sys.stdin.isatty():
        try:
            reply = input("Proceed? [y/N]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            reply = ""
        if reply not in ("y", "yes"):
            sys.exit("Aborted.")

    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        # Empty (checked above); shutil.move would otherwise nest src inside it.
        dst.rmdir()
    try:
        shutil.move(str(src), str(dst))
    except OSError as exc:
        sys.exit(f"Move failed: {exc}")

    # `drop=src` keeps the vacated path out of the remembered list -- it no
    # longer exists, so offering it for switching would only ever fail.
    saved = paths.set_configured_data_dir(dst, drop=src)
    environment.reset_cache()
    print(f"\nMoved.  Data directory is now {saved}")
    print(f"  recorded in {paths.config_path()}")
    # The .config marker rides along inside the moved tree, so the environment
    # follows the data rather than the path -- worth showing, since a move is
    # exactly when someone might expect it not to.
    print()
    _print_environment_block()

    env = os.environ.get(paths.ENV_VAR)
    if env and pathlib.Path(env).expanduser() == src:
        print(
            f"\n[note] {paths.ENV_VAR} still points at the old location.\n"
            f"       Unset it, or update it to {saved}."
        )


def _cmd_webserver(args: argparse.Namespace) -> None:
    import uvicorn
    from earthscope_positions.webserver.webserver import (
        app, set_public_base, run_startup_preflight,
    )

    # Blocking pre-flight: verify login (abort if not authed), seed coordinates,
    # and preload the default station/stream lists — all before we start serving.
    run_startup_preflight()

    set_public_base(args.hostname, args.port)
    env = environment.current()
    print(
        f"Starting GNSS Positions server → http://{args.hostname}:{args.port}"
        f"  (binding {args.host}:{args.port})"
    )
    print(f"  data directory: {paths.base_dir()}")
    print(f"  environment:    {env.label} ({env.name}) — {env.api_url}")
    uvicorn.run(app, host=args.host, port=args.port)


def _cmd_process_completeness(args: argparse.Namespace) -> None:
    from earthscope_positions.process.completeness import _GAP_SECONDS, generate_all

    gap_seconds = args.gap_seconds if args.gap_seconds is not None else _GAP_SECONDS
    if gap_seconds <= 0:
        sys.exit("--gap-seconds must be positive.")

    data_dir = paths.arrow_dir()

    if not data_dir.exists():
        sys.exit(f"Data directory not found: {data_dir}")

    from earthscope_positions.process.completeness import is_source_arrow
    arrow_files = [p for p in sorted(data_dir.rglob("*.arrow")) if is_source_arrow(p)]
    if not arrow_files:
        print(f"No .arrow files found under {data_dir}", file=sys.stderr)
        sys.exit(0)

    n_total = len(arrow_files)
    print(
        f"Scanning {n_total} Arrow file(s) under {data_dir} …"
        + (" (overwrite mode)" if args.overwrite else ""),
        file=sys.stderr,
    )
    print(f"  gap threshold: > {gap_seconds:g} s between samples", file=sys.stderr)

    generated = generate_all(
        data_dir,
        overwrite=args.overwrite,
        sampling_hz=args.sampling_hz,
        gap_seconds=gap_seconds,
    )

    skipped = n_total - len(generated)
    print(
        f"Done.  Generated: {len(generated)}  |  "
        f"Skipped (already up to date): {skipped}",
        file=sys.stderr,
    )


def _cmd_process_ppsd(args: argparse.Namespace) -> None:
    import datetime as _dt
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from earthscope_positions.export.ppsd_writer import (
        cache_path_for, compute_ppsd_cache, load_ppsd_cache,
    )

    data_dir = paths.arrow_dir()
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
    data_dir = paths.arrow_dir()
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
    ap, process_p, web_p, test_p, export_p, replay_p, config_p = _build_top_parser()

    if len(sys.argv) == 1:
        ap.print_help()
        sys.exit(0)

    # parse_known_args so we can forward all remaining tokens (including --help)
    # to the delegated module's parser, which gives correct per-command help.
    args, remaining = ap.parse_known_args()

    group = args.group

    # Allow the first-run data-directory prompt only for an interactive
    # terminal, and never for `config` (which reports on the setting, so
    # prompting first would be backwards) or `inspect` (explicit file paths,
    # no data directory involved).
    paths.set_interactive(
        sys.stdin.isatty() and group not in ("config", "inspect")
    )

    # In a container, refuse to run against a data directory that is not on a
    # mount -- everything written there dies with the container.  `config` and
    # `inspect` are exempt: they are how you diagnose the problem, so they must
    # keep working while it exists.
    if group not in ("config", "inspect"):
        problems = paths.container_data_dir_problems()
        if problems:
            sys.exit("\n".join(["Refusing to start:", ""] + problems))
        for note in paths.container_data_dir_notes():
            print(f"[note] {note}", file=sys.stderr)

    if group == "lists":
        sys.argv = ["es-pos lists"] + remaining
        from earthscope_positions.stations.station_list import main as _main
        _main()

    elif group == "stations":
        sys.exit(
            "'es-pos stations' is now 'es-pos lists' — it manages station lists as\n"
            "well as stream lists.  Command names changed too:\n"
            "  es-pos stations get datasource   ->  es-pos lists get-streams\n"
            "  es-pos stations get radial       ->  es-pos lists get-radial-streams\n"
            "  es-pos stations filter           ->  es-pos lists filter-streams\n"
            "New: get-stations, get-radial-stations, list, show-streams, show-stations.\n"
            "Run 'es-pos lists --help' for the full set."
        )

    elif group == "fetch":
        sys.argv = ["es-pos fetch"] + remaining
        from earthscope_positions.fetch.positions_fetch import main as _main
        _main()

    elif group == "config":
        config_cmd = getattr(args, "config_cmd", None)
        if config_cmd == "show":
            _cmd_config_show(args)
        elif config_cmd == "list-data-dirs":
            _cmd_config_list_data_dirs(args)
        elif config_cmd == "use-data-dir":
            _cmd_config_use_data_dir(args)
        elif config_cmd == "forget-data-dir":
            _cmd_config_forget_data_dir(args)
        elif config_cmd == "set-data-dir":
            _cmd_config_set_data_dir(args)
        elif config_cmd == "move-data-dir":
            _cmd_config_move_data_dir(args)
        else:
            config_p.print_help()
            sys.exit(0)

    elif group == "inspect":
        sys.argv = ["es-pos inspect"] + remaining
        from earthscope_positions.arrow_inspect import main as _main
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

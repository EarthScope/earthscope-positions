"""
station_list - discover and manage GNSS PPP position stream lists.

CLI subcommands:
  get datasource  search /discover/datasource/stream (earthscope-sdk)
  get radial      search /discover/gnss/radial (direct REST — no SDK method)
  filter          merge and filter existing stream list files
"""

import argparse
import pathlib
import sys
from typing import Optional, get_args

import orjson

from earthscope_positions import paths
from earthscope_sdk import EarthScopeClient
from earthscope_sdk.client.discovery.models import (
    ProcessingFacility,
    StreamSoftware,
    StreamType,
)

# Base host for the one endpoint the SDK doesn't cover (radial search).
_API_HOST = "https://api.earthscope.org"

# The SDK discovery calls auto-paginate up to `limit`; use a high cap for "all".
_MAX_RESULTS = 1_000_000


def _project_root() -> pathlib.Path:
    return paths.project_root()


# ---------------------------------------------------------------------------
# EarthScope SDK client (handles auth + token refresh internally)
# ---------------------------------------------------------------------------

_client: "EarthScopeClient | None" = None


def _discover():
    """Return the SDK discovery service, creating the shared client on first use."""
    global _client
    if _client is None:
        _client = EarthScopeClient()
    return _client.discover


def close_client() -> None:
    """Close the shared SDK client, releasing its underlying async httpx client
    and retry context.

    A short-lived CLI process that skips this leaves the SDK's async
    ``RetrySettings.retry_context`` generator pending until interpreter shutdown,
    which (depending on GC timing) prints spurious warnings — "Task was destroyed
    but it is pending!" and "coroutine method 'aclose' … was never awaited".
    Closing explicitly while the event loop is still healthy avoids that race.
    """
    global _client
    if _client is not None:
        try:
            if not _client.is_closed:
                _client.close()
        except Exception:
            pass
        _client = None


# ---------------------------------------------------------------------------
# API error handling
# ---------------------------------------------------------------------------

def _api_error(exc: Exception) -> None:
    """Print a clean API error message and exit (CLI use)."""
    resp = getattr(exc, "response", None)
    status = getattr(resp, "status_code", None)
    body = getattr(resp, "text", None)
    if status is not None:
        print(f"API error {status}:", file=sys.stderr)
        if body:
            print(f"  {body[:500]}", file=sys.stderr)
    else:
        print(f"API error: {exc}", file=sys.stderr)
    sys.exit(1)


# ---------------------------------------------------------------------------
# Record helpers
# ---------------------------------------------------------------------------

def _record(edid: str, geosncl: Optional[str], facility, software) -> dict:
    """Build a stream-list record.  facility/software are plain strings now
    (the SDK returns them as strings rather than enums)."""
    return {
        "geosncl": geosncl,
        "edid": edid,
        "facility": facility,
        "software": software,
    }


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------

def _validate_station_names(names: list[str]) -> None:
    bad_prefix = [n for n in names if not any(n.startswith(p) for p in _VALID_STATION_PREFIXES)]
    if bad_prefix:
        prefixes = ", ".join(_VALID_STATION_PREFIXES)
        sys.exit(
            f"Invalid station name(s): {bad_prefix}\n"
            f"Each name must start with one of: {prefixes}\n"
            f"Wildcard patterns are not allowed.\n"
            f"Examples:  4CHARID:P146  IGS:P14600USA  PNUM:123"
        )
    bad_wildcard = [n for n in names if "*" in n or "?" in n]
    if bad_wildcard:
        sys.exit(
            f"Wildcard patterns are not allowed in station names: {bad_wildcard}\n"
            f"Examples:  4CHARID:P146  IGS:P14600USA  PNUM:123"
        )

    _SUFFIX_LENGTHS = {"IGS:": 9, "4CHARID:": 4, "PNUM:": 4}
    bad_length = []
    for name in names:
        for prefix, length in _SUFFIX_LENGTHS.items():
            if name.startswith(prefix):
                suffix = name[len(prefix):]
                if len(suffix) != length:
                    bad_length.append(f"{name!r} ({prefix} suffix must be exactly {length} characters, got {len(suffix)})")
    if bad_length:
        sys.exit("Invalid station name(s):\n" + "".join(f"  {e}\n" for e in bad_length))


# ---------------------------------------------------------------------------
# get datasource
# ---------------------------------------------------------------------------

def _get_datasource(args) -> list[dict]:
    """List /discover/datasource/stream with stream_type=gnss_ppp (auto-paginated)."""
    if args.station_name:
        _validate_station_names(args.station_name)

    try:
        streams = _discover().list_stream_datasources(
            stream_type=StreamType.GNSS_PPP,
            facility=args.facility or None,
            software=args.software or None,
            label=args.label or None,
            station_name=args.station_name or None,
            network_name=args.network_name or None,
            limit=_MAX_RESULTS,
        )
    except Exception as exc:
        _api_error(exc)

    records = [
        _record(s.edid, s.names.get("GEOSNCL"), s.facility, s.software)
        for s in streams
    ]
    print(f"  {len(records)} stream(s) found", file=sys.stderr)
    return records


# ---------------------------------------------------------------------------
# Programmatic helpers (used by the webserver Station/Stream List Builder pages)
# ---------------------------------------------------------------------------

def list_networks(namespaces: tuple[str, ...] = ("RTDB", "SHAKE")) -> list[str]:
    """Return sorted, fully-qualified network names in the given namespaces.

    Lists /discover/datasource/network and keeps networks that have a name in one
    of *namespaces* (e.g. ``"SHAKE:NOTA"``, ``"RTDB:PBO"``).  ``names`` is a dict
    keyed by namespace (``{"SHAKE": "NOTA", ...}``).

    Raises on API failure (callers decide how to surface it).
    """
    nets = _discover().list_network_datasources(limit=_MAX_RESULTS)
    names: set[str] = set()
    for net in nets:
        nm = getattr(net, "names", None) or {}
        for ns in namespaces:
            val = nm.get(ns)
            if val:
                names.add(f"{ns}:{val}")
    return sorted(names)


def network_geosncls(network_name: str) -> list[str]:
    """Return geosncls of all gnss_ppp streams in *network_name*.

    Lists /discover/datasource/stream filtered by stream_type=gnss_ppp and the
    given network; the network filter already scopes results to that network's
    streams.

    Raises on API failure.
    """
    streams = _discover().list_stream_datasources(
        stream_type=StreamType.GNSS_PPP,
        network_name=network_name,
        limit=_MAX_RESULTS,
    )
    out = {gs for s in streams if (gs := s.names.get("GEOSNCL"))}
    return sorted(out)


def network_records(network_name: str) -> list[dict]:
    """Return full stream-list records (edid + geosncl + facility + software)
    for all gnss_ppp streams in *network_name*.  Deduplicated by edid/geosncl.

    Raises on API failure.
    """
    streams = _discover().list_stream_datasources(
        stream_type=StreamType.GNSS_PPP,
        network_name=network_name,
        limit=_MAX_RESULTS,
    )
    seen: set[str] = set()
    records: list[dict] = []
    for s in streams:
        gs = s.names.get("GEOSNCL")
        key = s.edid or gs or ""
        if not key or key in seen:
            continue
        seen.add(key)
        records.append(_record(s.edid, gs, s.facility, s.software))
    return records


def _sanitize_list_name(name: str) -> str:
    """Turn an arbitrary network name into a lowercase, dash-separated list name.

    e.g. ``"SHAKE:ORGN"`` -> ``"shake-orgn"``.
    """
    import re
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "network"


def save_network_list(network_name: str, list_name: Optional[str] = None) -> tuple[str, list[dict]]:
    """Fetch every gnss_ppp stream in *network_name* and save it as a station
    list (full records, so it stays fetchable).  Returns (list_name, records)."""
    records = network_records(network_name)
    name = _sanitize_list_name(list_name or network_name)
    _write(records, _resolve_output(name))
    return name, records


# ---------------------------------------------------------------------------
# Station lists (station codes only) + startup preload
# ---------------------------------------------------------------------------

def _station_of(gs: Optional[str]) -> Optional[str]:
    """Station code (FCID) from a geosncl, upper-cased (e.g. 'P143')."""
    if not gs:
        return None
    head = gs.split(".")[0].strip().upper()
    return head or None


def network_stations(network_name: str) -> list[str]:
    """Sorted unique station codes for all gnss_ppp streams in
    *network_name* (station names only — not the individual streams).

    Raises on API failure.
    """
    streams = _discover().list_stream_datasources(
        stream_type=StreamType.GNSS_PPP,
        network_name=network_name,
        limit=_MAX_RESULTS,
    )
    stations = {station for s in streams if (station := _station_of(s.names.get("GEOSNCL")))}
    return sorted(stations)


def save_station_list(name: str, stations: list[str]) -> pathlib.Path:
    """Write a **station** list (``{"station": "P143"}`` per line) under
    ``<base>/station-lists/<name>.jsonl``.  Returns the written path."""
    out = paths.station_lists_dir() / f"{_sanitize_list_name(name)}.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    norm = sorted({s.strip().upper() for s in stations if s and s.strip()})
    lines = b"\n".join(orjson.dumps({"station": s}) for s in norm) + b"\n"
    out.write_bytes(lines)
    return out


def save_stream_list(name: str, records: list[dict]) -> pathlib.Path:
    """Write a **stream** list (full geosncl records) under
    ``<base>/stream-lists/<name>.jsonl``.  Returns the written path."""
    out = _resolve_output(_sanitize_list_name(name))
    _write(records, out)
    return out


def _records_and_stations(streams) -> tuple[list[dict], list[str]]:
    """Split an SDK stream iterable into (dedup'd stream records, unique stations)."""
    seen: set[str] = set()
    records: list[dict] = []
    stations: set[str] = set()
    for s in streams:
        gs = s.names.get("GEOSNCL")
        station = _station_of(gs)
        if station:
            stations.add(station)
        key = s.edid or gs or ""
        if key and key not in seen:
            seen.add(key)
            records.append(_record(s.edid, gs, s.facility, s.software))
    return records, sorted(stations)


def preload_default_lists(log=None) -> dict[str, int]:
    """Create the always-available default lists if any are missing, using at most
    two API queries:

      stream-lists/all-streams.jsonl     (every gnss_ppp stream)
      station-lists/all-stations.jsonl   (every station)
      stream-lists/shake-alert.jsonl     (SHAKE:ShakeAlert streams)
      station-lists/shake-alert.jsonl    (SHAKE:ShakeAlert stations)

    Returns a summary of what was created ({name: count}).  Raises on API failure.
    """
    def _say(msg: str) -> None:
        if log:
            log(msg)

    created: dict[str, int] = {}
    stream_dir = paths.stream_lists_dir()
    station_dir = paths.station_lists_dir()

    # ── all-streams / all-stations (single full query, only if either missing) ──
    need_all_stream = not (stream_dir / "all-streams.jsonl").exists()
    need_all_station = not (station_dir / "all-stations.jsonl").exists()
    if need_all_stream or need_all_station:
        _say("Preloading all gnss_ppp streams …")
        streams = _discover().list_stream_datasources(
            stream_type=StreamType.GNSS_PPP, limit=_MAX_RESULTS,
        )
        records, stations = _records_and_stations(streams)
        if need_all_stream:
            save_stream_list("all-streams", records)
            created["all-streams"] = len(records)
            _say(f"  all-streams: {len(records)} stream(s)")
        if need_all_station:
            save_station_list("all-stations", stations)
            created["all-stations"] = len(stations)
            _say(f"  all-stations: {len(stations)} station(s)")

    # ── shake-alert stream + station lists (single network query) ──────────────
    need_sa_stream = not (stream_dir / "shake-alert.jsonl").exists()
    need_sa_station = not (station_dir / "shake-alert.jsonl").exists()
    if need_sa_stream or need_sa_station:
        _say("Preloading SHAKE:ShakeAlert …")
        streams = _discover().list_stream_datasources(
            stream_type=StreamType.GNSS_PPP,
            network_name="SHAKE:ShakeAlert",
            limit=_MAX_RESULTS,
        )
        records, stations = _records_and_stations(streams)
        if need_sa_stream:
            save_stream_list("shake-alert", records)
            created["shake-alert (streams)"] = len(records)
            _say(f"  shake-alert streams: {len(records)}")
        if need_sa_station:
            save_station_list("shake-alert", stations)
            created["shake-alert (stations)"] = len(stations)
            _say(f"  shake-alert stations: {len(stations)}")

    return created


# ---------------------------------------------------------------------------
# get radial
# ---------------------------------------------------------------------------

def _get_radial(args) -> list[dict]:
    """Radial search (tier=stream, stream_type=gnss_ppp).

    NOTE: the earthscope-sdk has no radial/refpos search method, so this calls
    the REST endpoint directly, authenticating with the same bearer token the
    fetch path uses (managed by earthscope-cli / earthscope-sdk credentials).
    """
    import requests
    from earthscope_positions.fetch.positions_fetch import _ensure_token

    params: dict = {
        "latitude": args.latitude,
        "longitude": args.longitude,
        "distance": args.distance,
        "tier": "stream",
        "stream_type": "gnss_ppp",
        "with_information": True,
    }
    if args.network_name:
        params["network"] = args.network_name
    if args.facility:
        params["facility"] = args.facility

    url = f"{_API_HOST}/beta/discover/gnss/radial"
    try:
        resp = requests.get(
            url,
            params=params,
            headers={
                "accept": "application/json",
                "authorization": f"Bearer {_ensure_token()}",
            },
            timeout=120,
        )
    except Exception as exc:
        sys.exit(f"Radial search request failed: {exc}")

    if resp.status_code != 200:
        print(f"API error {resp.status_code}:", file=sys.stderr)
        print(f"  {resp.text[:500]}", file=sys.stderr)
        sys.exit(1)

    data = resp.json()
    items = data.get("items", data) if isinstance(data, dict) else data
    if not items:
        return []

    software = args.software or None
    records = []
    for info in items:
        if isinstance(info, str):
            records.append(_record(info, None, None, None))
            continue
        sw = info.get("software")
        if software is not None and sw != software:
            continue
        records.append(_record(info.get("edid"), info.get("geosncl"),
                               info.get("facility"), sw))
    return records


# ---------------------------------------------------------------------------
# filter / merge
# ---------------------------------------------------------------------------

def _resolve_input(name: str) -> pathlib.Path:
    """Find an input file, checking data/stream-lists/ and adding .jsonl if needed."""
    sl = paths.stream_lists_dir()
    p = pathlib.Path(name)
    stem = p.stem if p.suffix in (".jsonl", ".json") else p.name
    candidates = [
        p,
        p.parent / (stem + ".jsonl"),
        sl / p.name,
        sl / (stem + ".jsonl"),
        sl / (stem + ".json"),        # backward compat
    ]
    for c in dict.fromkeys(candidates):
        if c.exists():
            return c
    tried = [str(c) for c in dict.fromkeys(candidates)]
    sys.exit(f"Input file not found: {name!r}\nTried: {tried}")


def _load_list(path: pathlib.Path) -> list[dict]:
    try:
        if path.suffix == ".json":
            data = orjson.loads(path.read_bytes())
            if not isinstance(data, list):
                sys.exit(f"Expected a JSON array in {path}, got {type(data).__name__}")
            return data
        # JSONL: one record per line
        return [
            orjson.loads(line)
            for line in path.read_bytes().splitlines()
            if line.strip()
        ]
    except Exception as exc:
        sys.exit(f"Failed to read {path}: {exc}")


def _do_filter(args) -> list[dict]:
    # Merge all inputs, deduplicate by edid
    merged: dict[str, dict] = {}
    for path_str in args.input:
        for rec in _load_list(_resolve_input(path_str)):
            edid = rec.get("edid")
            if edid:
                merged[edid] = rec
            else:
                # records without edid are kept but can't be deduped
                merged[id(rec)] = rec  # type: ignore[index]

    records = list(merged.values())
    print(f"Merged {len(records)} unique records from {len(args.input)} file(s).", file=sys.stderr)

    if getattr(args, "facility", None):
        keep = set(args.facility)
        records = [r for r in records if r.get("facility") in keep]

    if getattr(args, "software", None):
        keep = set(args.software)
        records = [r for r in records if r.get("software") in keep]

    if getattr(args, "geosncl", None):
        import fnmatch
        patterns = args.geosncl
        records = [
            r for r in records
            if r.get("geosncl") and any(fnmatch.fnmatch(r["geosncl"], p) for p in patterns)
        ]

    if getattr(args, "exclude_facility", None):
        ex = set(args.exclude_facility)
        records = [r for r in records if r.get("facility") not in ex]

    if getattr(args, "exclude_software", None):
        ex = set(args.exclude_software)
        records = [r for r in records if r.get("software") not in ex]

    return records


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def _resolve_output(name: str) -> pathlib.Path:
    """Resolve an output name to a path under <project_root>/data/stream-lists/, adding .jsonl if needed."""
    p = pathlib.Path(name)
    stem = p.stem if p.suffix in (".jsonl", ".json") else p.name
    p = pathlib.Path(stem + ".jsonl")
    if p.parent == pathlib.Path("."):
        p = paths.stream_lists_dir() / p.name
    return p


def _write(records: list[dict], output: Optional[pathlib.Path]) -> None:
    records = sorted(records, key=lambda r: (r.get("geosncl") is None, r.get("geosncl") or ""))
    lines = b"\n".join(orjson.dumps(rec) for rec in records) + b"\n"
    if output is None:
        sys.stdout.buffer.write(lines)
        print(
            f"\n{len(records)} records shown above. Add -o <name> to save to data/stream-lists/<name>.jsonl",
            file=sys.stderr,
        )
    else:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(lines)
        print(f"Wrote {len(records)} records → {output}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

_FACILITY_CHOICES = list(get_args(ProcessingFacility))
_SOFTWARE_CHOICES = list(get_args(StreamSoftware))

_VALID_STATION_PREFIXES = ("4CHARID:", "IGS:", "PNUM:")

_NETWORK_CHOICES = [
    "SHAKE:ShakeAlert",
    "SHAKE:NOTA",
    "SHAKE:PNGA",
    "SHAKE:WSRN",
    "SHAKE:BARD",
    "SHAKE:SCGN",
    "SHAKE:CRTN",
    "SHAKE:NCGN",
    "SHAKE:ORGN",
    "SHAKE:WCDA",
    "SHAKE:IGS",
    "SHAKE:UNKN",
    "RTDB:REALTIME",
]


def _add_data_dir_arg(p: argparse.ArgumentParser) -> None:
    """Add the standard --data-directory flag (stream lists live under <base>/stream-lists)."""
    p.add_argument(
        "--data-directory",
        metavar="PATH",
        default=None,
        help=(
            "Base data directory (default: $ES_POS_DATA_DIRECTORY or ./data).  "
            "Stream lists are read from / written to <PATH>/stream-lists."
        ),
    )


def _build_parser(prog=None) -> tuple[argparse.ArgumentParser, argparse.ArgumentParser]:
    ap = argparse.ArgumentParser(
        prog=prog,
        description=(
            "Discover and manage GNSS PPP position stream lists.\n\n"
            "stream_type=gnss_ppp is always set for API calls.\n"
            "For 'get radial', tier=stream is always set.\n\n"
            "Stream lists can also be built interactively via the Stream List Builder\n"
            "tab in the web UI ('es-pos webserver'), which shows all stations on a\n"
            "map and lets you filter by processing center and PPP solution type."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = ap.add_subparsers(dest="command")

    # ------------------------------------------------------------------ get
    get_p = sub.add_parser(
        "get",
        help="Fetch a stream list from the EarthScope API",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    get_sub = get_p.add_subparsers(dest="source")

    # -- get datasource
    ds_p = get_sub.add_parser(
        "datasource",
        help="Search /discover/datasource/stream",
        description=(
            "Query the stream datasource discovery endpoint.\n"
            "stream_type=gnss_ppp is always applied.\n\n"
            "Good starting point:\n"
            "  station_list get datasource --network-name SHAKE:ShakeAlert -o ShakeAlert"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ds_p.add_argument(
        "-o", "--output",
        default=None,
        metavar="NAME",
        help="Output list name; written to ./data/stream-lists/<name>.jsonl. Omit to print to screen.",
    )
    ds_p.add_argument(
        "--facility",
        choices=_FACILITY_CHOICES,
        metavar="FACILITY",
        help=f"Filter by processing facility. Choices: {_FACILITY_CHOICES}",
    )
    ds_p.add_argument(
        "--software",
        choices=_SOFTWARE_CHOICES,
        metavar="SOFTWARE",
        help=f"Filter by processing software. Choices: {_SOFTWARE_CHOICES}",
    )
    ds_p.add_argument(
        "--label",
        metavar="TEXT",
        help="Free-form label text to filter on",
    )
    ds_p.add_argument(
        "--station-name",
        nargs="+",
        metavar="NAME",
        help=(
            "Station name(s); must start with 4CHARID:, IGS:, or PNUM:.\n"
            "Wildcard patterns are not allowed.\n"
            "Examples:  4CHARID:P146  IGS:P14600USA  PNUM:123"
        ),
    )
    ds_p.add_argument(
        "--network-name",
        nargs="+",
        choices=_NETWORK_CHOICES,
        metavar="NETWORK",
        help=(
            f"Network name(s).  Valid choices:\n"
            + "".join(f"  {n}\n" for n in _NETWORK_CHOICES)
        ),
    )

    # -- get radial
    rad_p = get_sub.add_parser(
        "radial",
        help="Search /refpos/search/radial",
        description=(
            "Radial search for GNSS PPP streams around a center point.\n"
            "tier=stream and stream_type=gnss_ppp are always applied."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    rad_p.add_argument(
        "-o", "--output",
        required=True,
        metavar="FILE",
        help="Output list name or path; written to ./data/stream-lists/<name>.jsonl by default",
    )
    rad_p.add_argument(
        "--latitude",
        type=float,
        required=True,
        metavar="DEG",
        help="Center latitude in decimal degrees (−90 to 90)",
    )
    rad_p.add_argument(
        "--longitude",
        type=float,
        required=True,
        metavar="DEG",
        help="Center longitude in decimal degrees (−180 to 180)",
    )
    rad_p.add_argument(
        "--distance",
        type=float,
        required=True,
        metavar="KM",
        help="Search radius in km (Haversine great-circle distance)",
    )
    rad_p.add_argument(
        "--network-name",
        nargs="+",
        choices=_NETWORK_CHOICES,
        metavar="NETWORK",
        help=(
            f"Network name(s).  Valid choices:\n"
            + "".join(f"  {n}\n" for n in _NETWORK_CHOICES)
        ),
    )
    rad_p.add_argument(
        "--facility",
        choices=_FACILITY_CHOICES,
        metavar="FACILITY",
        help=f"Filter streams by processing facility. Choices: {_FACILITY_CHOICES}",
    )
    rad_p.add_argument(
        "--software",
        choices=_SOFTWARE_CHOICES,
        metavar="SOFTWARE",
        help=(
            f"Filter results by processing software (applied locally after the API call).\n"
            f"Choices: {_SOFTWARE_CHOICES}"
        ),
    )

    # --------------------------------------------------------------- filter
    filt_p = sub.add_parser(
        "filter",
        help="Merge and filter existing stream list JSONL files",
        description=(
            "Load one or more stream list files, merge them (deduplicating by edid),\n"
            "apply optional filters, and write the result to a new file."
        ),
        formatter_class=argparse.RawTextHelpFormatter,
    )
    filt_p.add_argument(
        "-i", "--input",
        action="append",
        required=True,
        metavar="FILE",
        help="Input file; repeat for multiple: -i ShakeAlert -i cwu  (data/stream-lists/ and .jsonl resolved automatically)",
    )
    filt_p.add_argument(
        "-o", "--output",
        default=None,
        metavar="NAME",
        help="Output list name; written to ./data/stream-lists/<name>.jsonl. Omit to print to screen.",
    )
    filt_p.add_argument(
        "--facility",
        nargs="+",
        choices=_FACILITY_CHOICES,
        metavar="FACILITY",
        help=(
            "Keep only records with these facility values (repeatable). Valid values:\n"
            + "".join(f"  {v}\n" for v in _FACILITY_CHOICES)
        ),
    )
    filt_p.add_argument(
        "--software",
        nargs="+",
        choices=_SOFTWARE_CHOICES,
        metavar="SOFTWARE",
        help=(
            "Keep only records with these software values (repeatable). Valid values:\n"
            + "".join(f"  {v}\n" for v in _SOFTWARE_CHOICES)
        ),
    )
    filt_p.add_argument(
        "--geosncl",
        nargs="+",
        metavar="PATTERN",
        help=(
            "Keep records whose geosncl matches any of these patterns.\n"
            "Wildcards (* ?) are supported.  Examples:\n"
            "  --geosncl 'P146.*'  --geosncl '*.PB.*' 'P147.*'"
        ),
    )
    filt_p.add_argument(
        "--exclude-facility",
        nargs="+",
        choices=_FACILITY_CHOICES,
        metavar="FACILITY",
        help=(
            "Remove records with these facility values. Valid values:\n"
            + "".join(f"  {v}\n" for v in _FACILITY_CHOICES)
        ),
    )
    filt_p.add_argument(
        "--exclude-software",
        nargs="+",
        choices=_SOFTWARE_CHOICES,
        metavar="SOFTWARE",
        help=(
            "Remove records with these software values. Valid values:\n"
            + "".join(f"  {v}\n" for v in _SOFTWARE_CHOICES)
        ),
    )

    for _p in (ds_p, rad_p, filt_p):
        _add_data_dir_arg(_p)

    return ap, get_p


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

def main() -> None:
    ap, get_p = _build_parser()
    args = ap.parse_args()

    if not args.command:
        ap.print_help()
        sys.exit(0)

    paths.set_base_dir(getattr(args, "data_directory", None))

    try:
        if args.command == "get":
            if not getattr(args, "source", None):
                get_p.print_help()
                sys.exit(0)

            output = _resolve_output(args.output) if args.output else None

            if args.source == "datasource":
                records = _get_datasource(args)
            else:
                records = _get_radial(args)
            _write(records, output)

        elif args.command == "filter":
            output = _resolve_output(args.output) if args.output else None
            records = _do_filter(args)
            print(f"After filtering: {len(records)} records.", file=sys.stderr)
            _write(records, output)
    finally:
        # Release the SDK client so this CLI process exits cleanly (no pending
        # async retry-context warnings at interpreter shutdown).
        close_client()


if __name__ == "__main__":
    main()

"""
station_list - discover and manage GNSS PPP position stream station lists.

CLI subcommands:
  get datasource  search /discover/datasource/stream
  get radial      search /refpos/search/radial
  filter          merge and filter existing station list files
"""

import argparse
import pathlib
import subprocess
import sys
from typing import Optional

import orjson

from earthscope_sdk.config.models import Tokens
from earthscope_client.api.discover_api import DiscoverApi
from earthscope_client.api_client import ApiClient
from earthscope_client.configuration import Configuration
from earthscope_client.exceptions import ApiException
from earthscope_client.models.facility import Facility
from earthscope_client.models.reference_position_tier import ReferencePositionTier
from earthscope_client.models.stream_software import StreamSoftware
from earthscope_client.models.stream_type import StreamType

# stream_info.py uses StreamType/Facility/StreamSoftware as forward references but
# never imports them, so pydantic can't resolve the model without help.
import earthscope_client.models.stream_info as _stream_info_mod
from earthscope_client.models.stream_info import StreamInfo
from earthscope_client.models.response_radial_search_streams_refpos_search_radial_get import (
    ResponseRadialSearchStreamsRefposSearchRadialGet,
)
_stream_info_mod.StreamType = StreamType  # type: ignore[attr-defined]
_stream_info_mod.Facility = Facility  # type: ignore[attr-defined]
_stream_info_mod.StreamSoftware = StreamSoftware  # type: ignore[attr-defined]
StreamInfo.model_rebuild()
ResponseRadialSearchStreamsRefposSearchRadialGet.model_rebuild()


_TOKENS_PATH = pathlib.Path.home() / ".earthscope" / "default" / "tokens.json"


def _project_root() -> pathlib.Path:
    """Walk up from CWD to find the project root (directory containing pyproject.toml)."""
    for p in [pathlib.Path.cwd(), *pathlib.Path.cwd().parents]:
        if (p / "pyproject.toml").exists():
            return p
    return pathlib.Path.cwd()
_PAGE_SIZE = 100
# Refresh if less than this many seconds remain
_REFRESH_MARGIN = 60


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

def _read_tokens() -> Tokens:
    try:
        raw = _TOKENS_PATH.read_bytes()
    except FileNotFoundError:
        sys.exit(
            f"No credentials found at {_TOKENS_PATH}.\n"
            "Please authenticate first:  es user login"
        )
    return Tokens.model_validate_json(raw)


def _ensure_token() -> str:
    """Return a valid Bearer access token, refreshing via earthscope-cli if needed."""
    tokens = _read_tokens()

    try:
        body = tokens.access_token_body
    except ValueError:
        body = None

    if body is not None and body.ttl.total_seconds() > _REFRESH_MARGIN:
        return tokens.access_token.get_secret_value()  # type: ignore[union-attr]

    print("Access token expired or near expiry; refreshing...", file=sys.stderr)
    result = subprocess.run(
        ["es", "user", "refresh-access-token"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        sys.exit(
            f"Token refresh failed:\n{result.stderr.strip()}\n\n"
            "Please re-authenticate:  es user login"
        )

    # Re-read from disk after refresh
    tokens = _read_tokens()
    try:
        body = tokens.access_token_body
    except ValueError:
        body = None

    if body is None or tokens.access_token is None:
        sys.exit(
            "Unable to obtain a valid access token after refresh.\n"
            "Please re-authenticate:  es user login"
        )

    remaining = int(body.ttl.total_seconds())
    print(f"Token refreshed; valid for {remaining}s.", file=sys.stderr)
    return tokens.access_token.get_secret_value()


# ---------------------------------------------------------------------------
# API error handling
# ---------------------------------------------------------------------------

def _api_error(exc: ApiException) -> None:
    """Print a clean API error message and exit."""
    messages = []

    # Prefer the deserialized data (HTTPValidationError for 422s has a .detail list)
    detail = getattr(getattr(exc, "data", None), "detail", None)
    if detail:
        for err in detail:
            msg = getattr(err, "msg", None)
            if msg:
                inp = getattr(err, "input", None)
                line = f"  {msg}"
                if inp is not None:
                    line += f" (got: {inp!r})"
                messages.append(line)

    # Fall back to parsing the raw JSON body
    if not messages and exc.body:
        try:
            import json as _json
            body = _json.loads(exc.body)
            for item in body.get("detail", []):
                if isinstance(item, dict) and "msg" in item:
                    line = f"  {item['msg']}"
                    if "input" in item:
                        line += f" (got: {item['input']!r})"
                    messages.append(line)
        except Exception:
            pass

    print(f"API error {exc.status} {exc.reason or ''}:", file=sys.stderr)
    for msg in messages:
        print(msg, file=sys.stderr)
    if not messages and exc.body:
        print(f"  {exc.body[:500]}", file=sys.stderr)
    sys.exit(1)


# ---------------------------------------------------------------------------
# API client factory
# ---------------------------------------------------------------------------

def _make_api(token: str) -> DiscoverApi:
    conf = Configuration(access_token=token)
    return DiscoverApi(api_client=ApiClient(configuration=conf))


# ---------------------------------------------------------------------------
# Record helpers
# ---------------------------------------------------------------------------

def _record(edid: str, geosncl: Optional[str], facility, software) -> dict:
    return {
        "geosncl": geosncl,
        "edid": edid,
        "facility": facility.value if facility is not None else None,
        "software": software.value if software is not None else None,
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
    """Paginate through /discover/datasource/stream with stream_type=gnss_ppp."""
    token = _ensure_token()
    api = _make_api(token)

    if args.station_name:
        _validate_station_names(args.station_name)

    facility = Facility(args.facility) if args.facility else None
    software = StreamSoftware(args.software) if args.software else None

    records: list[dict] = []
    offset = 0

    try:
        while True:
            resp = api.find_stream_datasources(
                stream_type=StreamType.GNSS_PPP,
                facility=facility,
                software=software,
                label=args.label or None,
                station_name=args.station_name or None,
                network_name=args.network_name or None,
                limit=_PAGE_SIZE,
                offset=offset,
            )

            page = resp.actual_instance
            if page is None or not hasattr(page, "items"):
                break

            for stream in page.items:
                geosncl = stream.names.geosncl if stream.names else None
                records.append(_record(stream.edid, geosncl, stream.facility, stream.software))

            print(
                f"  page offset={offset}: {len(page.items)} records (total so far: {len(records)})",
                file=sys.stderr,
            )

            if not page.has_next:
                break
            offset += _PAGE_SIZE

    except ApiException as exc:
        _api_error(exc)

    return records


# ---------------------------------------------------------------------------
# get radial
# ---------------------------------------------------------------------------

def _get_radial(args) -> list[dict]:
    """Search /refpos/search/radial with tier=stream, stream_type=gnss_ppp."""
    token = _ensure_token()
    api = _make_api(token)

    facility = Facility(args.facility) if args.facility else None
    software = StreamSoftware(args.software) if args.software else None

    try:
        resp = api.find_gnss_stations_radial(
            latitude=args.latitude,
            longitude=args.longitude,
            distance=args.distance,
            tier=ReferencePositionTier.STREAM,
            network=args.network_name or None,
            stream_type=StreamType.GNSS_PPP,
            facility=facility,
            with_information=True,
        )
    except ApiException as exc:
        _api_error(exc)

    items = resp.actual_instance
    if not items:
        return []

    records = []
    for info in items:
        if isinstance(info, str):
            records.append(_record(info, None, None, None))
        else:
            if software is not None and info.software != software:
                continue
            records.append(_record(info.edid, info.geosncl, info.facility, info.software))

    return records


# ---------------------------------------------------------------------------
# filter / merge
# ---------------------------------------------------------------------------

def _resolve_input(name: str) -> pathlib.Path:
    """Find an input file, checking data/station-lists/ and adding .jsonl if needed."""
    sl = _project_root() / "data" / "station-lists"
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
    """Resolve an output name to a path under <project_root>/data/station-lists/, adding .jsonl if needed."""
    p = pathlib.Path(name)
    stem = p.stem if p.suffix in (".jsonl", ".json") else p.name
    p = pathlib.Path(stem + ".jsonl")
    if p.parent == pathlib.Path("."):
        p = _project_root() / "data" / "station-lists" / p.name
    return p


def _write(records: list[dict], output: Optional[pathlib.Path]) -> None:
    records = sorted(records, key=lambda r: (r.get("geosncl") is None, r.get("geosncl") or ""))
    lines = b"\n".join(orjson.dumps(rec) for rec in records) + b"\n"
    if output is None:
        sys.stdout.buffer.write(lines)
        print(
            f"\n{len(records)} records shown above. Add -o <name> to save to data/station-lists/<name>.jsonl",
            file=sys.stderr,
        )
    else:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(lines)
        print(f"Wrote {len(records)} records → {output}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

_FACILITY_CHOICES = [f.value for f in Facility]
_SOFTWARE_CHOICES = [s.value for s in StreamSoftware]

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


def _build_parser(prog=None) -> tuple[argparse.ArgumentParser, argparse.ArgumentParser]:
    ap = argparse.ArgumentParser(
        prog=prog,
        description=(
            "Discover and manage GNSS PPP position stream station lists.\n\n"
            "stream_type=gnss_ppp is always set for API calls.\n"
            "For 'get radial', tier=stream is always set.\n\n"
            "Station lists can also be built interactively via the Station Builder\n"
            "tab in the web UI ('es-pos webserver'), which shows all stations on a\n"
            "map and lets you filter by processing center and PPP solution type."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = ap.add_subparsers(dest="command")

    # ------------------------------------------------------------------ get
    get_p = sub.add_parser(
        "get",
        help="Fetch a station list from the EarthScope API",
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
        help="Output list name; written to ./data/station-lists/<name>.jsonl. Omit to print to screen.",
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
        help="Output list name or path; written to ./data/station-lists/<name>.jsonl by default",
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
        help="Merge and filter existing station list JSONL files",
        description=(
            "Load one or more station list files, merge them (deduplicating by edid),\n"
            "apply optional filters, and write the result to a new file."
        ),
        formatter_class=argparse.RawTextHelpFormatter,
    )
    filt_p.add_argument(
        "-i", "--input",
        action="append",
        required=True,
        metavar="FILE",
        help="Input file; repeat for multiple: -i ShakeAlert -i cwu  (data/station-lists/ and .jsonl resolved automatically)",
    )
    filt_p.add_argument(
        "-o", "--output",
        default=None,
        metavar="NAME",
        help="Output list name; written to ./data/station-lists/<name>.jsonl. Omit to print to screen.",
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


if __name__ == "__main__":
    main()

"""
station_list - build and inspect GNSS PPP stream lists and station lists.

Backs the ``es-pos lists`` command group.  Two kinds of list are managed:
stream lists (full geosncl records, under <base>/stream-lists/) and station
lists (station codes only, under <base>/station-lists/), mirroring the Stream
List Builder and Station Builder tabs in the web UI.

CLI subcommands:
  list                 available lists of both kinds, with entry counts
  show-streams         print / --path / --edit a stream list
  show-stations        print / --path / --edit a station list
  get-streams          search /discover/datasource/stream (earthscope-sdk)
  get-stations         the same search, saved as station codes
  get-radial-streams   search /discover/gnss/radial (direct REST — no SDK method)
  get-radial-stations  the same search, saved as station codes
  filter-streams       merge and filter existing stream lists
"""

import argparse
import os
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

_GEOSNCL_NS_PREFIX = "GEOSNCL:"


def _normalize_geosncl(gs: Optional[str]) -> Optional[str]:
    """Strip the namespace prefix the radial endpoint puts on geosncl.

    /discover/gnss/radial returns names as ``"GEOSNCL:P156.NC.LY_.20"`` while
    /discover/datasource/stream returns the bare ``"P156.NC.LY_.20"``.  Left
    alone the prefix rides into saved stream lists, and every consumer that
    splits on "." then reads the station as ``"GEOSNCL:P156"`` -- note that
    ``parse_geosncl`` does *not* raise on it (the dot count is still 4), it
    just returns the wrong station, so this has to be normalised at ingestion.
    """
    if not gs:
        return gs
    return gs[len(_GEOSNCL_NS_PREFIX):] if gs.startswith(_GEOSNCL_NS_PREFIX) else gs


def _record(edid: str, geosncl: Optional[str], facility, software) -> dict:
    """Build a stream-list record.  facility/software are plain strings now
    (the SDK returns them as strings rather than enums)."""
    return {
        "geosncl": _normalize_geosncl(geosncl),
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


def _normalize_stations(stations: list[str]) -> list[str]:
    """Upper-cased, de-duplicated, sorted -- the on-disk form of a station list."""
    return sorted({s.strip().upper() for s in stations if s and s.strip()})


def save_station_list(name: str, stations: list[str]) -> pathlib.Path:
    """Write a **station** list (``{"station": "P143"}`` per line) under
    ``<base>/station-lists/<name>.jsonl``.  Returns the written path."""
    out = paths.station_lists_dir() / f"{_sanitize_list_name(name)}.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    norm = _normalize_stations(stations)
    out.write_bytes(b"\n".join(orjson.dumps({"station": s}) for s in norm) + b"\n")
    return out


def save_stream_list(name: str, records: list[dict]) -> pathlib.Path:
    """Write a **stream** list (full geosncl records) under
    ``<base>/stream-lists/<name>.jsonl``.  Returns the written path."""
    out = _resolve_output(_sanitize_list_name(name))
    _write(records, out)
    return out


# ---------------------------------------------------------------------------
# Stream-list record validation
# ---------------------------------------------------------------------------

#: The canonical stream-list record.  Every field is required: `edid` is the
#: datasource id the fetch API is queried with (without it every request 422s
#: and reads as "no data"), and facility/software are what the builders filter
#: on.  A partial record silently degrades everything downstream, so lists are
#: validated on write rather than tolerated on read.
STREAM_RECORD_FIELDS = ("geosncl", "edid", "facility", "software")

#: The generated superset of every gnss_ppp stream.  Treated as read-only: it
#: is the membership reference every other list is checked against, so an
#: edited copy would quietly invalidate them all.
ALL_STREAMS_LIST = "all-streams"


def validate_stream_record(rec: object) -> str | None:
    """Return an error describing why *rec* is not a valid stream record, else None."""
    if not isinstance(rec, dict):
        return f"expected a JSON object, got {type(rec).__name__}"
    missing = [f for f in STREAM_RECORD_FIELDS if not str(rec.get(f) or "").strip()]
    if missing:
        return f"missing or empty field(s): {', '.join(missing)}"
    extra = [k for k in rec if k not in STREAM_RECORD_FIELDS]
    if extra:
        return f"unexpected field(s): {', '.join(sorted(extra))}"
    geosncl = str(rec["geosncl"])
    try:
        parse_geosncl_parts(geosncl)
    except ValueError as exc:
        return str(exc)
    return None


def parse_geosncl_parts(geosncl: str) -> tuple[str, str, str, str]:
    """Split a geosncl into (station, network, channel base, location).

    Raises ``ValueError`` with a usable message when the shape is wrong -- the
    same four-part STATION.NETWORK.CHAN.LOC form the export path specs assume.
    """
    parts = geosncl.split(".")
    if len(parts) != 4:
        raise ValueError(
            f"geosncl {geosncl!r} must be STATION.NETWORK.CHAN.LOC (4 dot-separated parts)")
    if any(not p.strip() for p in parts):
        raise ValueError(f"geosncl {geosncl!r} has an empty part")
    return parts[0], parts[1], parts[2], parts[3]


def validate_stream_list_text(
    text: str, known_geosncls: "set[str] | None" = None,
) -> list[str]:
    """Validate raw JSONL stream-list text.  Returns human-readable errors.

    When *known_geosncls* is given, every record must also appear in it -- the
    all-streams superset.  A stream missing from that set is either a typo or a
    stream added to the API since all-streams was last generated; both need
    looking at rather than being written into a list that will later fail to
    fetch.
    """
    import orjson as _orjson

    errors: list[str] = []
    seen: set[str] = set()
    for i, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            rec = _orjson.loads(stripped)
        except Exception as exc:
            errors.append(f"line {i}: invalid JSON ({exc})")
            continue
        problem = validate_stream_record(rec)
        if problem:
            errors.append(f"line {i}: {problem}")
            continue
        geosncl = str(rec["geosncl"])
        if geosncl in seen:
            errors.append(f"line {i}: duplicate geosncl {geosncl}")
        seen.add(geosncl)
        if known_geosncls is not None and geosncl not in known_geosncls:
            errors.append(
                f"line {i}: {geosncl} is not in '{ALL_STREAMS_LIST}' — refresh it, "
                f"or remove this stream")
    return errors


def read_stream_list_records(name: str) -> list[dict]:
    """Records in ``<base>/stream-lists/<name>.jsonl`` (unvalidated)."""
    import orjson as _orjson

    path = paths.stream_lists_dir() / f"{name}.jsonl"
    if not path.exists():
        return []
    out: list[dict] = []
    for line in path.read_bytes().splitlines():
        if not line.strip():
            continue
        try:
            rec = _orjson.loads(line)
        except Exception:
            continue
        if isinstance(rec, dict):
            out.append(rec)
    return out


def all_stream_geosncls() -> set[str]:
    """Every geosncl in the all-streams list — the membership reference."""
    return {
        str(r["geosncl"]) for r in read_stream_list_records(ALL_STREAMS_LIST)
        if r.get("geosncl")
    }


def read_station_list(name: str) -> list[str]:
    """Station codes in ``<base>/station-lists/<name>.jsonl`` (upper, sorted, unique).

    An empty list if the file is absent; a malformed line is skipped rather
    than failing the whole read, so one bad hand-edit does not make a list
    unusable.
    """
    path = paths.station_lists_dir() / f"{name}.jsonl"
    if not path.exists():
        return []
    out: set[str] = set()
    for line in path.read_bytes().splitlines():
        if not line.strip():
            continue
        try:
            rec = orjson.loads(line)
        except orjson.JSONDecodeError:
            continue
        station = str(rec.get("station") or "").strip().upper()
        if station:
            out.add(station)
    return sorted(out)


def network_station_list(
    network_name: str, *, refresh: bool = False,
) -> tuple[str, list[str], bool]:
    """Station list for *network_name*, creating it on first use.

    Returns ``(list_name, stations, from_cache)``.

    The saved list is the point: loading a network should leave behind a
    reusable station list, not just an in-memory selection.  Once it exists it
    is read from disk instead of re-querying -- a full network query is slow,
    and a user who has since hand-edited the list would otherwise have their
    edits silently overwritten on the next load.  Pass ``refresh=True`` to
    re-query and overwrite deliberately.
    """
    name = _sanitize_list_name(network_name)
    if not refresh:
        cached = read_station_list(name)
        if cached:
            return name, cached, True
    # Normalise before returning, not just before writing: otherwise a fresh
    # load hands back the API's ordering while a cached load hands back the
    # sorted file, and callers see the same request answered two ways.
    stations = _normalize_stations(network_stations(network_name))
    save_station_list(name, stations)
    return name, stations, False


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

def lists_dir(kind: str) -> pathlib.Path:
    """Directory holding lists of *kind* -- ``"streams"`` or ``"stations"``."""
    return paths.stream_lists_dir() if kind == "streams" else paths.station_lists_dir()


def _resolve_input(name: str, kind: str = "streams") -> pathlib.Path:
    """Find an input list file, adding .jsonl and checking the list dir."""
    sl = lists_dir(kind)
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

def _resolve_output(name: str, kind: str = "streams") -> pathlib.Path:
    """Resolve an output name to a path under the list dir, adding .jsonl if needed."""
    p = pathlib.Path(name)
    stem = p.stem if p.suffix in (".jsonl", ".json") else p.name
    p = pathlib.Path(stem + ".jsonl")
    if p.parent == pathlib.Path("."):
        p = lists_dir(kind) / p.name
    return p


def _write_stations(stations: list[str], output: Optional[pathlib.Path]) -> None:
    """Write a station list (one ``{"station": "P143"}`` per line), or print it."""
    norm = _normalize_stations(stations)
    lines = b"\n".join(orjson.dumps({"station": s}) for s in norm) + b"\n"
    if output is None:
        sys.stdout.buffer.write(lines)
        print(
            f"\n{len(norm)} stations shown above. "
            f"Add -o <name> to save to {paths.station_lists_dir()}/<name>.jsonl",
            file=sys.stderr,
        )
    else:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(lines)
        print(f"Wrote {len(norm)} stations → {output}", file=sys.stderr)


def _stations_from_records(records: list[dict]) -> list[str]:
    """Unique station codes from stream records, in sorted order."""
    return sorted({st for r in records if (st := _station_of(r.get("geosncl")))})


def _entry_count(path: pathlib.Path) -> int:
    """Non-blank lines in a JSONL list; -1 if it cannot be read."""
    try:
        return sum(1 for line in path.read_bytes().splitlines() if line.strip())
    except OSError:
        return -1


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


def _add_discover_filters(p: argparse.ArgumentParser) -> None:
    """Filters shared by get-streams and get-stations (same API query, different output)."""
    p.add_argument(
        "--facility",
        choices=_FACILITY_CHOICES,
        metavar="FACILITY",
        help=f"Filter by processing facility. Choices: {_FACILITY_CHOICES}",
    )
    p.add_argument(
        "--software",
        choices=_SOFTWARE_CHOICES,
        metavar="SOFTWARE",
        help=f"Filter by processing software. Choices: {_SOFTWARE_CHOICES}",
    )
    p.add_argument(
        "--label",
        metavar="TEXT",
        help="Free-form label text to filter on",
    )
    p.add_argument(
        "--station-name",
        nargs="+",
        metavar="NAME",
        help=(
            "Station name(s); must start with 4CHARID:, IGS:, or PNUM:.\n"
            "Wildcard patterns are not allowed.\n"
            "Examples:  4CHARID:P146  IGS:P14600USA  PNUM:123"
        ),
    )
    p.add_argument(
        "--network-name",
        nargs="+",
        choices=_NETWORK_CHOICES,
        metavar="NETWORK",
        help=(
            "Network name(s).  Valid choices:\n"
            + "".join(f"  {n}\n" for n in _NETWORK_CHOICES)
        ),
    )


def _add_radial_args(p: argparse.ArgumentParser) -> None:
    """Centre point / radius shared by get-radial-streams and get-radial-stations."""
    p.add_argument(
        "--latitude", type=float, required=True, metavar="DEG",
        help="Center latitude in decimal degrees (−90 to 90)",
    )
    p.add_argument(
        "--longitude", type=float, required=True, metavar="DEG",
        help="Center longitude in decimal degrees (−180 to 180)",
    )
    p.add_argument(
        "--distance", type=float, required=True, metavar="KM",
        help="Search radius in km (Haversine great-circle distance)",
    )
    p.add_argument(
        "--network-name",
        nargs="+",
        choices=_NETWORK_CHOICES,
        metavar="NETWORK",
        help=(
            "Network name(s).  Valid choices:\n"
            + "".join(f"  {n}\n" for n in _NETWORK_CHOICES)
        ),
    )
    p.add_argument(
        "--facility",
        choices=_FACILITY_CHOICES,
        metavar="FACILITY",
        help=f"Filter streams by processing facility. Choices: {_FACILITY_CHOICES}",
    )
    p.add_argument(
        "--software",
        choices=_SOFTWARE_CHOICES,
        metavar="SOFTWARE",
        help=(
            "Filter results by processing software (applied locally after the API call).\n"
            f"Choices: {_SOFTWARE_CHOICES}"
        ),
    )


def _add_output_arg(p: argparse.ArgumentParser, kind: str, *, required: bool = False) -> None:
    where = "stream-lists" if kind == "streams" else "station-lists"
    p.add_argument(
        "-o", "--output",
        default=None,
        required=required,
        metavar="NAME",
        help=(
            f"Output list name; written to <data-directory>/{where}/<name>.jsonl."
            + ("" if required else "  Omit to print to screen.")
        ),
    )


def _build_parser(prog=None) -> tuple[argparse.ArgumentParser, argparse.ArgumentParser]:
    ap = argparse.ArgumentParser(
        prog=prog,
        description=(
            "Build and inspect the stream and station lists everything else runs on.\n\n"
            "Two kinds of list, mirroring the two builder tabs in the web UI:\n"
            "  stream lists   full geosncl records  (<data-directory>/stream-lists/)\n"
            "                 consumed by fetch, completeness, positions, ppsd,\n"
            "                 export and replay\n"
            "  station lists  station codes only    (<data-directory>/station-lists/)\n"
            "                 used as include/exclude sets when building stream lists\n\n"
            "stream_type=gnss_ppp is always set for API calls; the radial commands\n"
            "also always set tier=stream.\n\n"
            "Commands:\n"
            "  list                   Show every stream and station list, with entry counts\n"
            "  show-streams           Print a stream list (or just its path, with --path)\n"
            "  show-stations          Print a station list (or just its path, with --path)\n"
            "  get-streams            Query the API and save a stream list\n"
            "  get-stations           Query the API and save a station list\n"
            "  get-radial-streams     Radial search around a point, saved as a stream list\n"
            "  get-radial-stations    Radial search around a point, saved as a station list\n"
            "  filter-streams         Merge and filter existing stream lists\n"
            "  validate-streams       Check stream lists for incomplete records\n\n"
            "Both kinds can also be built interactively in the web UI\n"
            "('es-pos webserver') via the Station Builder and Stream List Builder tabs."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = ap.add_subparsers(dest="command")

    # ----------------------------------------------------------------- list
    list_p = sub.add_parser(
        "list",
        help="Show every stream and station list, with location and entry count.",
        description=(
            "List the stream and station lists available to this data directory,\n"
            "with how many entries each holds.\n\n"
            "Use 'show-streams NAME --path' or 'show-stations NAME --path' to get an\n"
            "absolute path for editing a list by hand."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    group = list_p.add_mutually_exclusive_group()
    group.add_argument(
        "--streams", action="store_true", help="Show only stream lists.",
    )
    group.add_argument(
        "--stations", action="store_true", help="Show only station lists.",
    )

    # ------------------------------------------------------------- show-*
    for cmd, kind, what in (
        ("show-streams", "streams", "stream"),
        ("show-stations", "stations", "station"),
    ):
        show_p = sub.add_parser(
            cmd,
            help=f"Print a {what} list, or just its path with --path.",
            description=(
                f"Print the contents of a {what} list.\n\n"
                f"--edit opens it in $VISUAL / $EDITOR and reports the entry count\n"
                f"afterwards, so a bad hand-edit is obvious straight away.\n\n"
                f"--path prints only the absolute path and nothing else, for\n"
                f"composing with other tools:\n"
                f"  es-pos lists {cmd} NAME --edit\n"
                f"  wc -l \"$(es-pos lists {cmd} NAME --path)\""
            ),
            formatter_class=argparse.RawDescriptionHelpFormatter,
        )
        show_p.add_argument("name", metavar="NAME", help=f"{what.capitalize()} list name.")
        show_g = show_p.add_mutually_exclusive_group()
        show_g.add_argument(
            "--edit", action="store_true",
            help="Open the list in $VISUAL / $EDITOR instead of printing it.",
        )
        show_g.add_argument(
            "--path", action="store_true",
            help="Print only the absolute file path, not the contents.",
        )

    # ------------------------------------------------------------ get-streams
    gs_p = sub.add_parser(
        "get-streams",
        help="Query the API and save a stream list.",
        description=(
            "Query the stream datasource discovery endpoint and save the matching\n"
            "streams as a stream list.  stream_type=gnss_ppp is always applied.\n\n"
            "Good starting point:\n"
            "  es-pos lists get-streams --network-name SHAKE:ShakeAlert -o ShakeAlert"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    _add_output_arg(gs_p, "streams")
    _add_discover_filters(gs_p)

    # ----------------------------------------------------------- get-stations
    gst_p = sub.add_parser(
        "get-stations",
        help="Query the API and save a station list.",
        description=(
            "Same query as get-streams, but saves the unique station codes instead\n"
            "of the full stream records -- the CLI equivalent of the web UI's\n"
            "Station Builder output.\n\n"
            "Station lists are the include/exclude sets the Stream List Builder\n"
            "works from; they are not directly fetchable (use a stream list for that).\n\n"
            "Example:\n"
            "  es-pos lists get-stations --network-name SHAKE:ShakeAlert -o ShakeAlert"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    _add_output_arg(gst_p, "stations")
    _add_discover_filters(gst_p)

    # ---------------------------------------------------- get-radial-streams
    grs_p = sub.add_parser(
        "get-radial-streams",
        help="Radial search around a point, saved as a stream list.",
        description=(
            "Radial search for GNSS PPP streams around a center point.\n"
            "tier=stream and stream_type=gnss_ppp are always applied.\n\n"
            "A 404 'No streams found' means nothing matched -- check that the centre\n"
            "point is on land and the radius actually reaches a station.\n\n"
            "Example:\n"
            "  es-pos lists get-radial-streams --latitude 40 --longitude -124 \\\n"
            "      --distance 500 -o humboldt"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    _add_output_arg(grs_p, "streams")
    _add_radial_args(grs_p)

    # --------------------------------------------------- get-radial-stations
    grst_p = sub.add_parser(
        "get-radial-stations",
        help="Radial search around a point, saved as a station list.",
        description=(
            "Same search as get-radial-streams, but saves the unique station codes\n"
            "instead of the full stream records.\n\n"
            "Example:\n"
            "  es-pos lists get-radial-stations --latitude 40 --longitude -124 \\\n"
            "      --distance 500 -o humboldt"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    _add_output_arg(grst_p, "stations")
    _add_radial_args(grst_p)

    # ------------------------------------------------------ validate-streams
    val_p = sub.add_parser(
        "validate-streams",
        help="Check stream lists for incomplete records.",
        description=(
            "Check that every line of every stream list is a complete record\n"
            "  {\"geosncl\", \"edid\", \"facility\", \"software\"}\n"
            "and that its stream appears in the all-streams reference.\n\n"
            "A record without an edid cannot be fetched -- the positions API is\n"
            "queried by EDID, and a geosncl does not parse as one -- so it fails\n"
            "silently as 'no data' rather than as an error.\n\n"
            "Exits non-zero if any list has problems.  With --fix, invalid lines\n"
            "are dropped and the file rewritten (a .bak copy is kept)."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    val_p.add_argument(
        "name", nargs="*", metavar="NAME",
        help="Stream list(s) to check.  Default: every list.",
    )
    val_p.add_argument(
        "--fix", action="store_true",
        help=("Repair each list from all-streams where possible, dropping only what "
              "cannot be resolved (saves <name>.jsonl.bak)."),
    )
    val_p.add_argument(
        "--quiet", "-q", action="store_true",
        help="Only print lists that have problems.",
    )

    # -------------------------------------------------------- filter-streams
    filt_p = sub.add_parser(
        "filter-streams",
        help="Merge and filter existing stream lists.",
        description=(
            "Load one or more stream lists, merge them (deduplicating by edid),\n"
            "apply optional filters, and write the result to a new stream list."
        ),
        formatter_class=argparse.RawTextHelpFormatter,
    )
    filt_p.add_argument(
        "-i", "--input",
        action="append",
        required=True,
        metavar="FILE",
        help="Input list; repeat for multiple: -i ShakeAlert -i cwu  (list dir and .jsonl resolved automatically)",
    )
    _add_output_arg(filt_p, "streams")
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

    return ap, list_p


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def _cmd_list(args) -> None:
    """Show the available lists of each kind, with entry counts."""
    show_streams = not args.stations
    show_stations = not args.streams
    sections = []
    if show_streams:
        sections.append(("Stream lists", "streams"))
    if show_stations:
        sections.append(("Station lists", "stations"))

    for i, (title, kind) in enumerate(sections):
        if i:
            print()
        directory = lists_dir(kind)
        files = sorted(directory.glob("*.jsonl")) if directory.is_dir() else []
        print(f"{title} ({len(files)})")
        if not directory.is_dir():
            print(f"  (no {directory} yet)")
            continue
        if not files:
            print(f"  (none in {directory})")
            continue
        width = max(len(f.stem) for f in files)
        for f in files:
            count = _entry_count(f)
            shown = "unreadable" if count < 0 else f"{count:,} entries"
            # Full path, not dir-header + filename: the path is the thing you
            # copy into an editor, and it should survive being read out of
            # scrollback without the header still being on screen.
            print(f"  {f.stem.ljust(width)}  {shown:>15}  {f.resolve()}")

    # stdout, not stderr: this is part of the listing, and on stderr it would
    # interleave ahead of the output it refers to.
    verb = "show-streams" if show_streams else "show-stations"
    print(f"\nEdit a list:  es-pos lists {verb} NAME --edit")


def _editor_command() -> list[str]:
    """The user's editor, as a command prefix.

    $VISUAL then $EDITOR, per POSIX convention; either may carry arguments
    (``EDITOR="code -w"``), so it is split as a shell word list rather than
    treated as a bare program name.  Falls back to the platform default only
    when it is actually installed -- exec'ing a missing `vi` would fail with a
    far less useful message than saying which variable to set.
    """
    import shlex
    import shutil

    for var in ("VISUAL", "EDITOR"):
        value = os.environ.get(var, "").strip()
        if value:
            parts = shlex.split(value)
            if parts:
                return parts
    fallback = "notepad" if sys.platform == "win32" else "vi"
    if shutil.which(fallback):
        return [fallback]
    sys.exit(
        "No editor configured.  Set $EDITOR (or $VISUAL), e.g.:\n"
        "  export EDITOR=nano\n"
        "Or edit the file directly -- 'es-pos lists show-... NAME --path' "
        "prints its location."
    )


def _cmd_show(args, kind: str) -> None:
    """Print a list's contents, or its path, or open it in an editor."""
    path = _resolve_input(args.name, kind)

    if args.path:
        print(path.resolve())
        return

    if args.edit:
        import subprocess
        cmd = [*_editor_command(), str(path.resolve())]
        before = _entry_count(path)
        try:
            code = subprocess.call(cmd)
        except OSError as exc:
            sys.exit(f"Could not launch editor {cmd[0]!r}: {exc}")
        if code != 0:
            sys.exit(f"Editor exited with status {code}; {path} left as it was.")
        after = _entry_count(path)
        delta = "" if after == before else f"  ({after - before:+,} from {before:,})"
        print(f"{path} — {after:,} entries{delta}", file=sys.stderr)
        if kind == "streams" and path.stem != ALL_STREAMS_LIST:
            # Catch a bad hand-edit now, while the file is still in mind, rather
            # than as a silent no-data result during a later fetch.
            known = all_stream_geosncls()
            errors = validate_stream_list_text(
                path.read_text(encoding="utf-8", errors="replace"), known or None)
            if errors:
                print(f"\n[warn] {len(errors)} problem(s) in this list:", file=sys.stderr)
                for e in errors[:5]:
                    print(f"  {e}", file=sys.stderr)
                if len(errors) > 5:
                    print(f"  … and {len(errors) - 5} more", file=sys.stderr)
                print("  Run 'es-pos lists validate-streams' for the full report.",
                      file=sys.stderr)
        return

    sys.stdout.buffer.write(path.read_bytes())
    print(f"\n{_entry_count(path)} entries in {path}", file=sys.stderr)


def _cmd_validate_streams(args) -> None:
    """Report (and optionally drop) stream-list records that cannot be fetched."""
    import orjson as _orjson

    directory = lists_dir("streams")
    if args.name:
        paths_to_check = [_resolve_input(n, "streams") for n in args.name]
    else:
        paths_to_check = sorted(directory.glob("*.jsonl"))
    if not paths_to_check:
        sys.exit("No stream lists found.")

    reference = {
        str(r["geosncl"]): r for r in read_stream_list_records(ALL_STREAMS_LIST)
        if r.get("geosncl")
    }
    known = set(reference)
    if known:
        print(f"Reference: {ALL_STREAMS_LIST} ({len(known):,} streams)\n")
    else:
        print(f"[warn] {ALL_STREAMS_LIST} is empty or missing — membership is not "
              f"being checked.\n")

    total_bad = 0
    for path in paths_to_check:
        name = path.stem
        text = path.read_text(encoding="utf-8", errors="replace")
        # all-streams is the reference; checking it against itself is circular.
        errors = validate_stream_list_text(
            text, None if name == ALL_STREAMS_LIST else (known or None))
        n_lines = sum(1 for l in text.splitlines() if l.strip())

        if not errors:
            if not args.quiet:
                print(f"  OK    {name:<28} {n_lines:>7,} record(s)")
            continue

        total_bad += 1
        print(f"  FAIL  {name:<28} {n_lines:>7,} record(s), {len(errors):,} problem(s)")
        for e in errors[:5]:
            print(f"          {e}")
        if len(errors) > 5:
            print(f"          … and {len(errors) - 5:,} more")

        if args.fix:
            # Repair before discarding.  These lists are mostly complete records
            # missing facility/software, and all-streams has those values -- so
            # fill them in and only drop what genuinely cannot be resolved.
            kept: list[dict] = []
            repaired = dropped = 0
            seen: set[str] = set()
            for line in text.splitlines():
                if not line.strip():
                    continue
                try:
                    rec = _orjson.loads(line)
                except Exception:
                    dropped += 1
                    continue
                geosncl = str(rec.get("geosncl") or "") if isinstance(rec, dict) else ""
                if validate_stream_record(rec) is None and geosncl not in seen:
                    if not known or geosncl in known:
                        seen.add(geosncl)
                        kept.append({f: rec[f] for f in STREAM_RECORD_FIELDS})
                        continue
                canonical = reference.get(geosncl)
                if canonical is not None and validate_stream_record(canonical) is None:
                    if geosncl not in seen:
                        seen.add(geosncl)
                        kept.append({f: canonical[f] for f in STREAM_RECORD_FIELDS})
                        repaired += 1
                    continue
                dropped += 1
            backup = path.with_suffix(".jsonl.bak")
            backup.write_text(text, encoding="utf-8")
            path.write_bytes(b"\n".join(_orjson.dumps(r) for r in kept) + b"\n")
            print(f"          fixed: {len(kept):,} record(s) kept "
                  f"({repaired:,} repaired from {ALL_STREAMS_LIST}, {dropped:,} dropped); "
                  f"original saved to {backup.name}")

    if total_bad:
        print(f"\n{total_bad} list(s) with problems."
              + ("" if args.fix else
                 f"  Re-run with --fix to repair them from {ALL_STREAMS_LIST}."))
        sys.exit(1)
    print(f"\nAll {len(paths_to_check)} list(s) valid.")


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

def main() -> None:
    ap, list_p = _build_parser()
    args = ap.parse_args()

    if not args.command:
        ap.print_help()
        sys.exit(0)

    try:
        if args.command == "list":
            _cmd_list(args)

        elif args.command == "show-streams":
            _cmd_show(args, "streams")

        elif args.command == "show-stations":
            _cmd_show(args, "stations")

        elif args.command == "get-streams":
            records = _get_datasource(args)
            _write(records, _resolve_output(args.output, "streams") if args.output else None)

        elif args.command == "get-stations":
            records = _get_datasource(args)
            _write_stations(
                _stations_from_records(records),
                _resolve_output(args.output, "stations") if args.output else None,
            )

        elif args.command == "get-radial-streams":
            records = _get_radial(args)
            _write(records, _resolve_output(args.output, "streams") if args.output else None)

        elif args.command == "get-radial-stations":
            records = _get_radial(args)
            _write_stations(
                _stations_from_records(records),
                _resolve_output(args.output, "stations") if args.output else None,
            )

        elif args.command == "validate-streams":
            _cmd_validate_streams(args)

        elif args.command == "filter-streams":
            records = _do_filter(args)
            print(f"After filtering: {len(records)} records.", file=sys.stderr)
            _write(records, _resolve_output(args.output, "streams") if args.output else None)
    finally:
        # Release the SDK client so this CLI process exits cleanly (no pending
        # async retry-context warnings at interpreter shutdown).
        close_client()


if __name__ == "__main__":
    main()

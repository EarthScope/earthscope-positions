"""
GeoJSON writer for GNSS position Arrow files.

Two output formats:

  compact  Newline-delimited JSON (NDJSON) — one record per sample:
             {"time":...,"Q":...,"type":"ENU","SNCL":"...","coor":[E,N,U],
              "err":[Eerr,Nerr,Uerr],"rate":1}

  full     GeoJSON FeatureCollection — all samples for the day as features:
             {"type":"FeatureCollection",
              "properties":{"sampleRate":1,"SNCL":"..."},
              "features":[
                {"type":"Feature",
                 "geometry":{"type":"Point","coordinates":[E,N,U]},
                 "properties":{"coordinateType":"ENU","time":...,
                               "EError":...,"NError":...,"UError":...,
                               "quality":...}},
                ...]}

Output paths are controlled by geojson_path_spec.toml.
"""
from __future__ import annotations

import datetime as dt
import pathlib
import re
import sys
import tomllib

import orjson


# ---------------------------------------------------------------------------
# geosncl helpers
# ---------------------------------------------------------------------------

def _geosncl_from_path(arrow_path: pathlib.Path) -> str:
    """Derive geosncl from canonical layout:  .../GEOSNCL/YYYYMM/file.arrow"""
    candidate = arrow_path.parent.parent.name
    if "." in candidate:
        return candidate
    m = re.match(r"^(.+?)_\d{8}T", arrow_path.stem)
    if m:
        return m.group(1)
    raise ValueError(f"Cannot derive geosncl from {arrow_path}")


def _parse_geosncl(geosncl: str) -> tuple[str, str, str, str]:
    """Return (station, network, chan_base, location)."""
    parts = geosncl.split(".")
    if len(parts) != 4:
        raise ValueError(f"Expected STATION.NETWORK.CHAN.LOC, got: {geosncl!r}")
    return parts[0], parts[1], parts[2], parts[3]


# ---------------------------------------------------------------------------
# Path spec (TOML)
# ---------------------------------------------------------------------------

_SPEC_DEFAULTS: dict = {
    "compact": {
        "root":      "data/geojson/compact",
        "directory": "{year}/{network}/{station}",
        "filename":  "{geosncl}.{year}.{julday}",
        "extension": ".jsonl",
        "options": {
            "round_decimals": None,   # None = full precision; set to e.g. 6 for cleaner output
        },
    },
    "full": {
        "root":      "data/geojson/full",
        "directory": "{year}/{network}/{station}",
        "filename":  "{geosncl}.{year}.{julday}",
        "extension": ".geojson",
        "options": {
            "compact_json":    True,
            "round_decimals":  6,
        },
    },
}


def load_spec(path: pathlib.Path | None) -> dict:
    """Load TOML path spec, filling missing keys from built-in defaults."""
    spec = _deep_merge({}, _SPEC_DEFAULTS)
    if path is not None:
        raw = tomllib.loads(path.read_text())
        spec = _deep_merge(spec, raw)
    return spec


def _deep_merge(base: dict, override: dict) -> dict:
    result = dict(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(result.get(k), dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result


def _out_path(section: dict, variables: dict) -> pathlib.Path:
    root      = pathlib.Path(section["root"])
    directory = section["directory"].format_map(variables)
    filename  = section["filename"].format_map(variables) + section["extension"]
    return root / directory / filename


def _path_vars(geosncl: str, station: str, network: str, location: str,
               chan_base: str, first_ms: int) -> dict:
    d = dt.datetime.fromtimestamp(first_ms / 1000, tz=dt.timezone.utc)
    return {
        "geosncl":  geosncl,
        "station":  station,
        "network":  network,
        "location": location,
        "channel":  chan_base,
        "year":     str(d.year),
        "month":    f"{d.month:02d}",
        "day":      f"{d.day:02d}",
        "julday":   f"{d.timetuple().tm_yday:03d}",
        "hour":     f"{d.hour:02d}",
    }


# ---------------------------------------------------------------------------
# Sample rate helper
# ---------------------------------------------------------------------------

def _sample_rate_hz(times_ms: list[int]) -> int | float:
    """Compute sample rate in Hz from a list of epoch-ms timestamps."""
    n = len(times_ms)
    if n < 2:
        return 1
    diffs = sorted(
        times_ms[i + 1] - times_ms[i]
        for i in range(min(200, n - 1))
        if times_ms[i + 1] != times_ms[i]
    )
    expected_ms = float(diffs[len(diffs) // 2]) if diffs else 1000.0
    hz = 1000.0 / expected_ms
    return int(hz) if hz == int(hz) else hz


# ---------------------------------------------------------------------------
# Compact (NDJSON) writer
# ---------------------------------------------------------------------------

def write_arrow_to_compact_json(
    arrow_path: pathlib.Path,
    spec: dict,
    *,
    geosncl: str | None = None,
    verbose: bool = True,
) -> pathlib.Path | None:
    """
    Write NDJSON — one JSON line per sample.
    Returns the output path, or None if the file had no samples.
    """
    import pyarrow.ipc as ipc

    table = ipc.open_stream(arrow_path).read_all()
    n_rows = len(table)
    if n_rows == 0:
        if verbose:
            print(f"  [skip] {arrow_path.name} -- no samples", file=sys.stderr)
        return None

    if geosncl is None:
        geosncl = _geosncl_from_path(arrow_path)
    station, network, chan_base, location = _parse_geosncl(geosncl)

    times:  list[int | None]   = table.column("time").to_pylist()
    east:   list[float | None] = table.column("east").to_pylist()
    north:  list[float | None] = table.column("north").to_pylist()
    up:     list[float | None] = table.column("up").to_pylist()
    sigEE:  list[float | None] = table.column("sigEE").to_pylist()
    sigNN:  list[float | None] = table.column("sigNN").to_pylist()
    sigUU:  list[float | None] = table.column("sigUU").to_pylist()
    q_col:  list[int | None]   = table.column("qChannel").to_pylist()

    valid_times = [t for t in times if t is not None]
    if not valid_times:
        return None

    rate = _sample_rate_hz(valid_times)

    section = spec["compact"]
    opts_c  = section.get("options", {})
    rd_c    = opts_c.get("round_decimals", None)

    def _rc(v: float | None) -> float | None:
        if v is None or rd_c is None:
            return v
        return round(v, rd_c)

    pvars = _path_vars(geosncl, station, network, location, chan_base, valid_times[0])
    out = _out_path(section, pvars)
    out.parent.mkdir(parents=True, exist_ok=True)

    n_written = 0
    with out.open("wb") as fh:
        for t, e, n, u, se, sn, su, q in zip(
            times, east, north, up, sigEE, sigNN, sigUU, q_col
        ):
            if t is None:
                continue

            coor = [_rc(e), _rc(n), _rc(u)] if (e is not None and n is not None and u is not None) else None
            err  = [_rc(se), _rc(sn), _rc(su)] if (se is not None and sn is not None and su is not None) else None

            record = {
                "time": t,
                "Q":    q,
                "type": "ENU",
                "SNCL": geosncl,
                "coor": coor,
                "err":  err,
                "rate": rate,
            }
            fh.write(orjson.dumps(record, option=orjson.OPT_SERIALIZE_NUMPY))
            fh.write(b"\n")
            n_written += 1

    if verbose:
        try:
            display = out.relative_to(pathlib.Path.cwd())
        except ValueError:
            display = out
        print(f"  compact  {display}  ({n_written:,} records, {out.stat().st_size:,} B)")

    return out


# ---------------------------------------------------------------------------
# Full GeoJSON writer
# ---------------------------------------------------------------------------

def write_arrow_to_full_geojson(
    arrow_path: pathlib.Path,
    spec: dict,
    *,
    geosncl: str | None = None,
    verbose: bool = True,
) -> pathlib.Path | None:
    """
    Write a GeoJSON FeatureCollection — one file per station-day.
    Samples with null east/north/up are skipped (Point must have coordinates).
    Returns the output path, or None if no valid samples.
    """
    import pyarrow.ipc as ipc

    table = ipc.open_stream(arrow_path).read_all()
    n_rows = len(table)
    if n_rows == 0:
        if verbose:
            print(f"  [skip] {arrow_path.name} -- no samples", file=sys.stderr)
        return None

    if geosncl is None:
        geosncl = _geosncl_from_path(arrow_path)
    station, network, chan_base, location = _parse_geosncl(geosncl)

    times:  list[int | None]   = table.column("time").to_pylist()
    east:   list[float | None] = table.column("east").to_pylist()
    north:  list[float | None] = table.column("north").to_pylist()
    up:     list[float | None] = table.column("up").to_pylist()
    sigEE:  list[float | None] = table.column("sigEE").to_pylist()
    sigNN:  list[float | None] = table.column("sigNN").to_pylist()
    sigUU:  list[float | None] = table.column("sigUU").to_pylist()
    q_col:  list[int | None]   = table.column("qChannel").to_pylist()

    opts    = spec["full"].get("options", {})
    rd      = opts.get("round_decimals", None)

    def _r(v: float | None) -> float | None:
        if v is None or rd is None:
            return v
        return round(v, rd)

    features = []
    valid_times: list[int] = []

    for t, e, n, u, se, sn, su, q in zip(
        times, east, north, up, sigEE, sigNN, sigUU, q_col
    ):
        if t is None or e is None or n is None or u is None:
            continue
        valid_times.append(t)
        features.append({
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [_r(e), _r(n), _r(u)],
            },
            "properties": {
                "coordinateType": "ENU",
                "time":           t,
                "EError":         _r(se),
                "NError":         _r(sn),
                "UError":         _r(su),
                "quality":        q,
            },
        })

    if not features:
        if verbose:
            print(f"  [skip] {arrow_path.name} -- no valid (non-null) samples",
                  file=sys.stderr)
        return None

    rate = _sample_rate_hz(valid_times)

    collection = {
        "type": "FeatureCollection",
        "properties": {
            "sampleRate": rate,
            "SNCL":       geosncl,
        },
        "features": features,
    }

    pvars = _path_vars(geosncl, station, network, location, chan_base, valid_times[0])
    section = spec["full"]
    out = _out_path(section, pvars)
    out.parent.mkdir(parents=True, exist_ok=True)

    json_opts = orjson.OPT_SERIALIZE_NUMPY
    if not opts.get("compact_json", True):
        json_opts |= orjson.OPT_INDENT_2

    out.write_bytes(orjson.dumps(collection, option=json_opts))

    if verbose:
        try:
            display = out.relative_to(pathlib.Path.cwd())
        except ValueError:
            display = out
        print(f"  full     {display}  ({len(features):,} features, {out.stat().st_size:,} B)")

    return out


# ---------------------------------------------------------------------------
# Convenience: write both formats from one Arrow file
# ---------------------------------------------------------------------------

def expected_out_paths(
    arrow_path: pathlib.Path,
    spec: dict,
    formats: tuple[str, ...] = ("compact", "full"),
) -> list[pathlib.Path]:
    """Return expected GeoJSON output paths from the filename alone (no file read)."""
    try:
        geosncl = _geosncl_from_path(arrow_path)
        station, network, chan_base, location = _parse_geosncl(geosncl)
    except ValueError:
        return []
    stem = arrow_path.stem
    prefix = geosncl + "_"
    if not stem.startswith(prefix):
        return []
    rest = stem[len(prefix):]
    if len(rest) < 8 or (len(rest) > 8 and rest[8] != "T"):
        return []
    try:
        file_date = dt.date(int(rest[:4]), int(rest[4:6]), int(rest[6:8]))
    except (ValueError, IndexError):
        return []
    d = dt.datetime(file_date.year, file_date.month, file_date.day, tzinfo=dt.timezone.utc)
    pvars = {
        "geosncl":  geosncl,
        "station":  station,
        "network":  network,
        "location": location,
        "channel":  chan_base,
        "year":     str(d.year),
        "month":    f"{d.month:02d}",
        "day":      f"{d.day:02d}",
        "julday":   f"{d.timetuple().tm_yday:03d}",
        "hour":     "00",
    }
    return [_out_path(spec[fmt], pvars) for fmt in formats if fmt in spec]


def write_arrow_to_geojson(
    arrow_path: pathlib.Path,
    spec: dict,
    *,
    geosncl: str | None = None,
    formats: tuple[str, ...] = ("compact", "full"),
    verbose: bool = True,
) -> list[pathlib.Path]:
    """Write one or both GeoJSON formats for an Arrow file. Returns written paths."""
    written: list[pathlib.Path] = []
    if "compact" in formats:
        p = write_arrow_to_compact_json(arrow_path, spec, geosncl=geosncl, verbose=verbose)
        if p:
            written.append(p)
    if "full" in formats:
        p = write_arrow_to_full_geojson(arrow_path, spec, geosncl=geosncl, verbose=verbose)
        if p:
            written.append(p)
    return written

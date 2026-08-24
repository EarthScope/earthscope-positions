"""
MiniSEED writer for GNSS position Arrow files.

One Arrow file -> 8 MiniSEED files, one per channel.
Gaps (null values or time jumps) split the output into separate records.

Record encoding and packing is done by `pymseed`, EarthScope's binding for the
C `libmseed` library -- this module only maps Arrow columns onto FDSN source
identifiers and output paths.

Channel mapping  (geosncl base "LY_" -> 3-char SEED channel code):
  LYE   East position           float64  metres      Arrow col: east
  LYN   North position          float64  metres      Arrow col: north
  LYZ   Up position             float64  metres      Arrow col: up
  LY1   East uncertainty        float64  metres      Arrow col: sigEE
  LY2   North uncertainty       float64  metres      Arrow col: sigNN
  LY3   Up uncertainty          float64  metres      Arrow col: sigUU
  LYQ   Quality channel         int32               Arrow col: qChannel
  LYL   Ingest latency          int32    ms          Arrow col: ingestLatency

FDSN Source Identifier:
  FDSN:{network}_{station}_{location}_{band}_{source}_{subsource}
  e.g.  FDSN:PW_DEEJ_00_L_Y_E

Format version 3 is the default.  Version 2 (classic SEED) is available via
the spec's `format_version` key or `--format-version 2`; it constrains the
record length to a power of two (see `_check_record_length`).

Note: records are written with the format's default flags.  The previous
hand-rolled writer set the "clock locked" record flag; libmseed's trace-list
packing API does not expose per-record flags, so that bit is no longer set.

Path layout is controlled by <data-directory>/resources/miniseed_path_spec.toml
(or pass --spec to override).
"""
from __future__ import annotations

import datetime as dt
import pathlib
import re
import sys
import tomllib
from typing import NamedTuple

from pymseed import DataEncoding, MS3TraceList


# Format versions this writer can emit.  3 is the default.
SUPPORTED_FORMAT_VERSIONS = (2, 3)
DEFAULT_FORMAT_VERSION = 3


# ---------------------------------------------------------------------------
# Channel definitions
# ---------------------------------------------------------------------------

class _Chan(NamedTuple):
    col:         str           # Arrow column name
    encoding:    DataEncoding  # miniSEED data encoding
    sample_type: str           # pymseed sample type code ('d'=float64, 'i'=int32)

# subsource_char -> channel definition
# Subsource letters match the actual ShakeAlert / geojson2ew channel codes:
#   E=east, N=north, Z=up, 1=sigE, 2=sigN, 3=sigU, Q=quality, L=ingest latency
CHANNELS: dict[str, _Chan] = {
    "E": _Chan("east",          DataEncoding.FLOAT64, "d"),  # metres
    "N": _Chan("north",         DataEncoding.FLOAT64, "d"),
    "Z": _Chan("up",            DataEncoding.FLOAT64, "d"),
    "1": _Chan("sigEE",         DataEncoding.FLOAT64, "d"),
    "2": _Chan("sigNN",         DataEncoding.FLOAT64, "d"),
    "3": _Chan("sigUU",         DataEncoding.FLOAT64, "d"),
    "Q": _Chan("qChannel",      DataEncoding.INT32,   "i"),
    "L": _Chan("ingestLatency", DataEncoding.INT32,   "i"),  # milliseconds
}

_INT32_MIN = -2_147_483_648
_INT32_MAX = 2_147_483_647


# ---------------------------------------------------------------------------
# geosncl -> SEED identifiers
# ---------------------------------------------------------------------------

class _GSID(NamedTuple):
    station:  str
    network:  str
    band:     str
    source:   str
    location: str

def parse_geosncl(geosncl: str) -> _GSID:
    """
    Parse 'DEEJ.PW.LY_.00' -> _GSID(station='DEEJ', network='PW',
                                     band='L', source='Y', location='00').
    Raises ValueError for unexpected formats.
    """
    parts = geosncl.split(".")
    if len(parts) != 4:
        raise ValueError(f"Expected STATION.NETWORK.CHAN.LOC, got: {geosncl!r}")
    station, network, chan_base, location = parts
    if len(chan_base) != 3 or chan_base[2] != "_":
        raise ValueError(f"Channel base must be 3 chars ending in '_': {chan_base!r}")
    return _GSID(station=station, network=network,
                 band=chan_base[0], source=chan_base[1], location=location)


def _geosncl_from_path(arrow_path: pathlib.Path) -> str:
    """Derive geosncl from canonical directory layout: .../GEOSNCL/YYYYMM/file.arrow"""
    candidate = arrow_path.parent.parent.name
    if "." in candidate:          # sanity-check: geosncl contains dots
        return candidate
    # Fall back to regex on the filename stem
    m = re.match(r"^(.+?)_\d{8}T", arrow_path.stem)
    if m:
        return m.group(1)
    raise ValueError(f"Cannot derive geosncl from {arrow_path}")


# ---------------------------------------------------------------------------
# Gap / null splitting
# ---------------------------------------------------------------------------

def split_on_gaps(
    times_ms: list[int],
    values: list,
    expected_ms: float,
    gap_factor: float,
) -> list[tuple[list[int], list]]:
    """
    Split (times_ms, values) into contiguous gap-free segments.

    A new segment starts when:
      - a value is None (null/missing sample), or
      - the time jump exceeds gap_factor * expected_ms

    Returns a list of (times, values) tuples -- no Nones, no inter-segment gaps.
    Each segment is handed to libmseed as one contiguous run of samples.
    """
    segments: list[tuple[list[int], list]] = []
    seg_t: list[int] = []
    seg_v: list      = []
    thresh = gap_factor * expected_ms

    for t, v in zip(times_ms, values):
        is_null = v is None
        is_gap  = bool(seg_t) and (t - seg_t[-1] > thresh)
        if is_null or is_gap:
            if seg_t:
                segments.append((seg_t, seg_v))
            seg_t, seg_v = [], []
        if not is_null:
            seg_t.append(t)
            seg_v.append(v)

    if seg_t:
        segments.append((seg_t, seg_v))
    return segments


# ---------------------------------------------------------------------------
# Format version / record length validation
# ---------------------------------------------------------------------------

def _check_format_version(version: int) -> int:
    if version not in SUPPORTED_FORMAT_VERSIONS:
        raise ValueError(
            f"Unsupported MiniSEED format version: {version!r} "
            f"(supported: {', '.join(map(str, SUPPORTED_FORMAT_VERSIONS))})"
        )
    return version


def _check_record_length(max_record_length: int, format_version: int) -> int:
    """
    Validate the record length up front so the failure names the spec key,
    rather than surfacing as a libmseed packing error mid-write.

    MiniSEED 2 records must be a power of two between 128 and 65536; MiniSEED 3
    records are variable-length, so the value is only an upper bound.
    """
    if max_record_length < 128 or max_record_length > 65536:
        raise ValueError(
            f"max_record_length must be between 128 and 65536 bytes, "
            f"got {max_record_length}"
        )
    if format_version == 2 and (max_record_length & (max_record_length - 1)) != 0:
        raise ValueError(
            f"MiniSEED 2 requires max_record_length to be a power of two "
            f"(512, 1024, 2048, 4096, ...); got {max_record_length}.  "
            f"Either set a power of two or use format_version = 3."
        )
    return max_record_length


# ---------------------------------------------------------------------------
# Path spec (TOML)
# ---------------------------------------------------------------------------

_SPEC_DEFAULTS: dict = {
    "root":      "data/miniseed",
    "directory": "{year}/{network}/{station}/{channel}.D",
    "filename":  "{network}.{station}.{location}.{channel}.D.{year}.{julday}",
    "extension": ".ms",
    "encoding": {
        "format_version":    DEFAULT_FORMAT_VERSION,
        "max_record_length": 4096,
        "gap_factor":        1.5,
    },
}

# Removed in favour of `max_record_length` (bytes), which is what libmseed
# packs to.  Specs written by earlier versions still carry the old key.
_LEGACY_ENCODING_KEYS = ("max_samples_per_record",)


def load_spec(path: pathlib.Path | None) -> dict:
    """Load TOML path spec, falling back to built-in defaults for missing keys."""
    spec = _deep_merge({}, _SPEC_DEFAULTS)
    if path is not None:
        raw = tomllib.loads(path.read_text())
        spec = _deep_merge(spec, raw)
    for key in _LEGACY_ENCODING_KEYS:
        if spec.get("encoding", {}).pop(key, None) is not None:
            print(
                f"[warn] '{key}' in the path spec is obsolete and was ignored; "
                f"record size is now controlled by 'max_record_length' (bytes).",
                file=sys.stderr,
            )
    return spec


def _deep_merge(base: dict, override: dict) -> dict:
    result = dict(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(result.get(k), dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result


def _out_path(spec: dict, variables: dict) -> pathlib.Path:
    root      = pathlib.Path(spec["root"])
    directory = spec["directory"].format_map(variables)
    filename  = spec["filename"].format_map(variables) + spec["extension"]
    return root / directory / filename


# ---------------------------------------------------------------------------
# Main conversion entry point
# ---------------------------------------------------------------------------

def expected_out_paths(arrow_path: pathlib.Path, spec: dict) -> list[pathlib.Path]:
    """Return the 8 expected MiniSEED output paths from the filename alone (no file read)."""
    try:
        geosncl = _geosncl_from_path(arrow_path)
        gsid = parse_geosncl(geosncl)
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
    doy_str = f"{d.timetuple().tm_yday:03d}"
    paths = []
    for subsource in CHANNELS:
        channel = f"{gsid.band}{gsid.source}{subsource}"
        variables = {
            "network":  gsid.network,
            "station":  gsid.station,
            "location": gsid.location,
            "channel":  channel,
            "geosncl":  geosncl,
            "year":     str(d.year),
            "month":    f"{d.month:02d}",
            "day":      f"{d.day:02d}",
            "julday":   doy_str,
            "hour":     "00",
        }
        paths.append(_out_path(spec, variables))
    return paths


def write_arrow_to_miniseed(
    arrow_path: pathlib.Path,
    spec: dict,
    *,
    geosncl: str | None = None,
    format_version: int | None = None,
    verbose: bool = True,
) -> list[pathlib.Path]:
    """
    Convert one Arrow file to 8 MiniSEED files (one per channel).

    `format_version` overrides the spec's `[encoding] format_version`
    (2 or 3; default 3).  Returns the list of written file paths.
    """
    import pyarrow.ipc as ipc

    enc_spec = spec["encoding"]
    version = _check_format_version(
        int(format_version if format_version is not None
            else enc_spec.get("format_version", DEFAULT_FORMAT_VERSION))
    )
    max_reclen = _check_record_length(int(enc_spec["max_record_length"]), version)
    gap_factor = float(enc_spec["gap_factor"])

    table  = ipc.open_stream(arrow_path).read_all()
    n_rows = len(table)

    if geosncl is None:
        geosncl = _geosncl_from_path(arrow_path)

    gsid = parse_geosncl(geosncl)

    times_ms: list[int] = table.column("time").to_pylist()
    if not times_ms:
        if verbose:
            print(f"  [skip] {arrow_path.name} -- no samples", file=sys.stderr)
        return []

    # Nominal sample interval from median of first 200 non-zero diffs
    probe = sorted(
        times_ms[i+1] - times_ms[i]
        for i in range(min(200, n_rows - 1))
        if times_ms[i+1] != times_ms[i]
    )
    expected_ms    = float(probe[len(probe) // 2]) if probe else 1000.0
    sample_rate_hz = 1000.0 / expected_ms

    first_dt = dt.datetime.fromtimestamp(times_ms[0] / 1000, tz=dt.timezone.utc)
    doy_str  = f"{first_dt.timetuple().tm_yday:03d}"

    written: list[pathlib.Path] = []

    for subsource, chan in CHANNELS.items():
        channel = f"{gsid.band}{gsid.source}{subsource}"      # e.g. LYE
        values: list = table.column(chan.col).to_pylist()
        segments = split_on_gaps(times_ms, values, expected_ms, gap_factor)
        if not segments:
            continue

        sid = (f"FDSN:{gsid.network}_{gsid.station}_{gsid.location}"
               f"_{gsid.band}_{gsid.source}_{subsource}")

        # One trace list per channel -> one output file.  libmseed splits each
        # segment into records of at most `max_reclen` bytes.
        traces = MS3TraceList()
        for seg_t, seg_v in segments:
            if chan.sample_type == "i":
                seg_v = [max(_INT32_MIN, min(_INT32_MAX, int(v))) for v in seg_v]
            traces.add_data(
                sourceid=sid,
                data_samples=seg_v,
                sample_type=chan.sample_type,
                sample_rate=sample_rate_hz,
                starttime=seg_t[0] * 1_000_000,   # ms since epoch -> ns since epoch
            )

        variables = {
            "network":  gsid.network,
            "station":  gsid.station,
            "location": gsid.location,
            "channel":  channel,
            "geosncl":  geosncl,
            "year":     str(first_dt.year),
            "month":    f"{first_dt.month:02d}",
            "day":      f"{first_dt.day:02d}",
            "julday":   doy_str,
            "hour":     f"{first_dt.hour:02d}",
        }
        out = _out_path(spec, variables)
        out.parent.mkdir(parents=True, exist_ok=True)
        n_rec = traces.to_file(
            out,
            overwrite=True,
            max_record_length=max_reclen,
            encoding=chan.encoding,
            format_version=version,
        )
        written.append(out)

        if verbose:
            try:
                display = out.relative_to(pathlib.Path.cwd())
            except ValueError:
                display = out
            print(f"  {channel}  {display}"
                  f"  ({out.stat().st_size:,} B, {n_rec} rec, "
                  f"{len(segments)} seg, v{version})")

    return written

"""
MiniSEED 3 writer for GNSS position Arrow files.

One Arrow file -> 8 MiniSEED 3 files, one per channel.
Gaps (null values or time jumps) split the output into separate records.

Channel mapping  (geosncl base "LY_" -> 3-char SEED channel code):
  LYE   East position           float64  metres      Arrow col: east
  LYN   North position          float64  metres      Arrow col: north
  LYZ   Up position             float64  metres      Arrow col: up
  LY1   East uncertainty        float64  metres      Arrow col: sigEE
  LY2   North uncertainty       float64  metres      Arrow col: sigNN
  LY3   Up uncertainty          float64  metres      Arrow col: sigUU
  LYQ   Quality channel         int32               Arrow col: qChannel
  LYL   Ingest latency          int32    ms          Arrow col: ingestLatency

FDSN Source Identifier (MiniSEED 3):
  FDSN:{network}_{station}_{location}_{band}_{source}_{subsource}
  e.g.  FDSN:PW_DEEJ_00_L_Y_E

Path layout is controlled by miniseed_path_spec.toml in the working directory
(or pass --spec to override).
"""
from __future__ import annotations

import datetime as dt
import pathlib
import re
import struct
import sys
import tomllib
from typing import NamedTuple


# ---------------------------------------------------------------------------
# CRC-32C (Castagnoli) -- no external dependency
# ---------------------------------------------------------------------------

def _build_crc32c_table() -> list[int]:
    poly = 0x82F63B78  # bit-reversed Castagnoli polynomial
    table = []
    for i in range(256):
        crc = i
        for _ in range(8):
            crc = (crc >> 1) ^ poly if crc & 1 else crc >> 1
        table.append(crc)
    return table

_CRC32C_TABLE = _build_crc32c_table()

def _crc32c(data: bytes) -> int:
    crc = 0xFFFF_FFFF
    for b in data:
        crc = (crc >> 8) ^ _CRC32C_TABLE[(crc ^ b) & 0xFF]
    return crc ^ 0xFFFF_FFFF


# ---------------------------------------------------------------------------
# Channel definitions
# ---------------------------------------------------------------------------

class _Chan(NamedTuple):
    col:      str   # Arrow column name
    encoding: int   # MiniSEED encoding (3=int32, 5=float64)

# subsource_char -> channel definition
# Subsource letters match the actual ShakeAlert / geojson2ew channel codes:
#   E=east, N=north, Z=up, 1=σE, 2=σN, 3=σU, Q=quality, L=ingest latency
CHANNELS: dict[str, _Chan] = {
    "E": _Chan("east",          5),  # float64, metres
    "N": _Chan("north",         5),
    "Z": _Chan("up",            5),
    "1": _Chan("sigEE",         5),
    "2": _Chan("sigNN",         5),
    "3": _Chan("sigUU",         5),
    "Q": _Chan("qChannel",      3),  # int32
    "L": _Chan("ingestLatency", 3),  # int32, milliseconds
}


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
# MiniSEED 3 record builder
# ---------------------------------------------------------------------------

# Fixed header: 40 bytes, all little-endian.
# Per IRISWS MiniSEED 3 specification:
#
# Offset  Size  Type     Field
#   0      2    CHAR     Record indicator ("MS")
#   2      1    UINT8    Format version (3)
#   3      1    UINT8    Flags
#   4      4    UINT32   Nanoseconds (0-999999999)
#   8      2    UINT16   Year
#  10      2    UINT16   Day of year (1-366)
#  12      1    UINT8    Hour
#  13      1    UINT8    Minute
#  14      1    UINT8    Second
#  15      1    UINT8    Data payload encoding
#  16      8    FLOAT64  Sample rate/period (positive = Hz)
#  24      4    UINT32   Number of samples
#  28      4    UINT32   CRC-32C (computed with this field zeroed)
#  32      1    UINT8    Data publication version
#  33      1    UINT8    Length of identifier (bytes)
#  34      2    UINT16   Length of extra headers (0 = none)
#  36      4    UINT32   Length of data payload (bytes)
# -------- variable --------
#  40     id_len  CHAR   FDSN Source Identifier
#  40+id  eh_len  CHAR   Extra headers JSON (absent when length=0)
#  40+id  data_len       Data payload

_HDR_FMT  = "<2sBBIHHBBBBdIIBBHI"
_HDR_SIZE = struct.calcsize(_HDR_FMT)
assert _HDR_SIZE == 40, f"Header size mismatch: {_HDR_SIZE}"


def _time_fields(ms: int) -> tuple[int, int, int, int, int, int]:
    """ms since Unix epoch -> (nanoseconds, year, doy, hour, minute, second)."""
    s, rem_ms = divmod(ms, 1000)
    d = dt.datetime.fromtimestamp(s, tz=dt.timezone.utc)
    return rem_ms * 1_000_000, d.year, d.timetuple().tm_yday, d.hour, d.minute, d.second


def _pack_payload(encoding: int, values: list) -> bytes:
    n = len(values)
    if encoding == 5:
        return struct.pack(f"<{n}d", *values)
    if encoding == 3:
        clamped = [max(-2_147_483_648, min(2_147_483_647, int(v))) for v in values]
        return struct.pack(f"<{n}i", *clamped)
    raise ValueError(f"Unsupported MiniSEED encoding: {encoding}")


def make_ms3_record(
    sid: str,
    start_ms: int,
    sample_rate_hz: float,
    encoding: int,
    values: list,
    flags: int = 0x04,   # bit 2 = clock locked (GPS receiver)
    pub_version: int = 1,
) -> bytes:
    """Build and return one complete MiniSEED 3 record as bytes."""
    sid_bytes = sid.encode("ascii")
    if len(sid_bytes) > 255:
        raise ValueError(f"Source identifier too long ({len(sid_bytes)} chars): {sid}")
    payload = _pack_payload(encoding, values)
    ns, yr, doy, hr, mi, sc = _time_fields(start_ms)

    hdr = struct.pack(
        _HDR_FMT,
        b"MS",           # record indicator
        3,               # format version
        flags,
        ns,              # sub-second nanoseconds
        yr, doy,         # start time (year + day-of-year)
        hr, mi, sc,      # start time (hour, minute, second)
        encoding,        # data encoding
        sample_rate_hz,  # positive Hz
        len(values),     # number of samples
        0,               # CRC placeholder
        pub_version,     # publication version
        len(sid_bytes),  # identifier length
        0,               # extra headers length (none)
        len(payload),    # data payload length
    )
    record = hdr + sid_bytes + payload
    crc = _crc32c(record)
    return record[:28] + struct.pack("<I", crc) + record[32:]


# ---------------------------------------------------------------------------
# Path spec (TOML)
# ---------------------------------------------------------------------------

_SPEC_DEFAULTS: dict = {
    "root":      "data/miniseed",
    "directory": "{year}/{network}/{station}/{channel}.D",
    "filename":  "{network}.{station}.{location}.{channel}.D.{year}.{julday}",
    "extension": ".ms",
    "encoding": {
        "max_samples_per_record": 4096,
        "gap_factor": 1.5,
    },
}


def load_spec(path: pathlib.Path | None) -> dict:
    """Load TOML path spec, falling back to built-in defaults for missing keys."""
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
    verbose: bool = True,
) -> list[pathlib.Path]:
    """
    Convert one Arrow file to 8 MiniSEED 3 files (one per channel).
    Returns the list of written file paths.
    """
    import pyarrow.ipc as ipc

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

    max_spr    = int(spec["encoding"]["max_samples_per_record"])
    gap_factor = float(spec["encoding"]["gap_factor"])

    first_dt = dt.datetime.fromtimestamp(times_ms[0] / 1000, tz=dt.timezone.utc)
    doy_str  = f"{first_dt.timetuple().tm_yday:03d}"

    written: list[pathlib.Path] = []

    for subsource, chan in CHANNELS.items():
        channel = f"{gsid.band}{gsid.source}{subsource}"      # e.g. LYX
        values: list = table.column(chan.col).to_pylist()
        segments = split_on_gaps(times_ms, values, expected_ms, gap_factor)
        if not segments:
            continue

        sid = (f"FDSN:{gsid.network}_{gsid.station}_{gsid.location}"
               f"_{gsid.band}_{gsid.source}_{subsource}")

        buf   = bytearray()
        n_rec = 0
        for seg_t, seg_v in segments:
            for i in range(0, len(seg_v), max_spr):
                chunk_t = seg_t[i : i + max_spr]
                chunk_v = seg_v[i : i + max_spr]
                buf += make_ms3_record(
                    sid=sid,
                    start_ms=chunk_t[0],
                    sample_rate_hz=sample_rate_hz,
                    encoding=chan.encoding,
                    values=chunk_v,
                )
                n_rec += 1

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
        out.write_bytes(bytes(buf))
        written.append(out)

        if verbose:
            try:
                display = out.relative_to(pathlib.Path.cwd())
            except ValueError:
                display = out
            print(f"  {channel}  {display}"
                  f"  ({len(buf):,} B, {n_rec} rec, {len(segments)} seg)")

    return written

"""
Station coordinate lookup from the merged coordinates.csv.

Priority in the source file (highest first):
  gage          GAGE GPS IGS14 solutions
  shakealert    ShakeAlert extended coordinates
  rtdb          RealTimeDB

Usage
-----
    from earthscope_positions.coordinates import Coordinates

    coords = Coordinates()                        # loads from default path
    c = coords.get("P143")                        # StationCoord or None
    c = coords["P143"]                             # same, raises KeyError if missing

    print(c.latitude, c.longitude, c.height, c.source)

    # Bulk lookup
    found = coords.lookup_all(["P143", "BEPK", "XXXX"])
    # found is dict[str, StationCoord | None]

The CSV is loaded once and cached in memory.  Pass a custom path to override
the default.

Editable copy
-------------
The default path is the **user-editable** copy in the data directory
(``<data-dir>/coordinates.csv``), seeded on first use from the bundled
``resources/coordinates.csv``.  Helpers here manage that copy:

    read_text()                current CSV text (seeding first)
    validate_and_normalize()   parse + validate uploaded/edited CSV text
    save_edited(text)          replace the file (Edit Coordinates)
    merge_upload(text)         merge an upload; uploaded rows win (Update)

``source`` is optional in uploaded/edited CSV — it defaults to ``"user"``.
"""
from __future__ import annotations

import csv
import io
import pathlib
import shutil
from dataclasses import dataclass
from functools import lru_cache
from typing import Iterable


# Bundled seed: <project_root>/resources/coordinates.csv
_RESOURCES_CSV = (
    pathlib.Path(__file__).resolve().parents[2]
    / "resources" / "coordinates.csv"
)

# CSV schema for the editable coordinates file.
_HEADER = ["station", "latitude", "longitude", "height", "source"]
_REQUIRED = ("station", "latitude", "longitude", "height")
_DEFAULT_SOURCE = "user"


def data_csv_path() -> pathlib.Path:
    """The editable data-directory coordinates CSV (``<data-dir>/coordinates.csv``)."""
    from earthscope_positions import paths  # local import avoids any import cycle
    return paths.coordinates_file()


def ensure_data_csv() -> pathlib.Path:
    """Return the editable data-dir CSV, seeding it from the bundled resources
    copy on first use so the user always has an editable file to start from."""
    dst = data_csv_path()
    if not dst.exists():
        dst.parent.mkdir(parents=True, exist_ok=True)
        if _RESOURCES_CSV.exists():
            shutil.copyfile(_RESOURCES_CSV, dst)
        else:
            dst.write_text(",".join(_HEADER) + "\n", encoding="utf-8")
    return dst


@dataclass(frozen=True, slots=True)
class StationCoord:
    station:   str
    latitude:  float
    longitude: float
    height:    float
    source:    str   # "gage" | "shakealert" | "rtdb"

    def __str__(self) -> str:
        return (f"{self.station}  lat={self.latitude:.6f}  lon={self.longitude:.6f}"
                f"  h={self.height:.3f} m  [{self.source}]")


class Coordinates:
    """In-memory coordinate table loaded from coordinates.csv."""

    def __init__(self, csv_path: pathlib.Path | str | None = None) -> None:
        path = pathlib.Path(csv_path) if csv_path is not None else ensure_data_csv()
        if not path.exists():
            raise FileNotFoundError(
                f"Coordinates file not found: {path}\n"
                "Run:  python resources/coordinates_generation/build_coordinates_csv.py  to regenerate it."
            )
        self._table: dict[str, StationCoord] = {}
        with path.open(newline="") as fh:
            for row in csv.DictReader(fh):
                station = row["station"].strip().upper()
                self._table[station] = StationCoord(
                    station=station,
                    latitude=float(row["latitude"]),
                    longitude=float(row["longitude"]),
                    height=float(row["height"]),
                    source=row["source"].strip(),
                )
        self._path = path

    # ------------------------------------------------------------------
    # Lookup API
    # ------------------------------------------------------------------

    def get(self, station: str) -> StationCoord | None:
        """Return the StationCoord for *station* (case-insensitive), or None."""
        return self._table.get(station.upper())

    def __getitem__(self, station: str) -> StationCoord:
        """Return the StationCoord for *station*, raising KeyError if absent."""
        try:
            return self._table[station.upper()]
        except KeyError:
            raise KeyError(f"Station not found: {station!r}") from None

    def __contains__(self, station: object) -> bool:
        return isinstance(station, str) and station.upper() in self._table

    def __len__(self) -> int:
        return len(self._table)

    def lookup_all(self, stations: Iterable[str]) -> dict[str, StationCoord | None]:
        """Look up multiple stations at once.  Returns dict with None for misses."""
        return {s: self._table.get(s.upper()) for s in stations}

    def all_stations(self) -> list[str]:
        """Sorted list of all known station codes."""
        return sorted(self._table)

    def __repr__(self) -> str:
        return f"Coordinates({len(self._table)} stations, source={self._path})"


# ---------------------------------------------------------------------------
# Module-level singleton (lazy-loaded)
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def _default_coords() -> Coordinates:
    return Coordinates()


def get(station: str) -> StationCoord | None:
    """Module-level shortcut: look up a station in the default Coordinates table."""
    return _default_coords().get(station)


# ---------------------------------------------------------------------------
# Editable-file management (validate / read / write / merge)
# ---------------------------------------------------------------------------

def _fmt(v: float) -> str:
    """Render a float without scientific notation, dropping a trailing '.0'."""
    s = f"{v!r}"
    return s


def validate_and_normalize(text: str) -> list[dict]:
    """Parse coordinates CSV *text*, validate it, and return normalized rows.

    Required columns (case-insensitive, any order): station, latitude, longitude,
    height.  ``source`` is optional and defaults to ``"user"``.  Raises
    ``ValueError`` with a human-readable, line-numbered message if anything is
    invalid.  Later duplicate stations within the text win over earlier ones.
    """
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        raise ValueError(
            "File is empty — expected a header row: station,latitude,longitude,height[,source]"
        )
    fmap = {(c or "").strip().lower(): c for c in reader.fieldnames}
    missing = [c for c in _REQUIRED if c not in fmap]
    if missing:
        raise ValueError(
            "Missing required column(s): " + ", ".join(missing)
            + f".  Header found: {', '.join(reader.fieldnames)}"
        )

    rows: list[dict] = []
    by_station: dict[str, int] = {}   # station -> index in rows (for de-dup)
    errors: list[str] = []

    for i, raw in enumerate(reader, start=2):     # line 1 is the header
        if all((v is None or str(v).strip() == "") for v in raw.values()):
            continue                              # skip blank lines

        station = str(raw.get(fmap["station"], "") or "").strip().upper()
        if not station:
            errors.append(f"line {i}: missing station")
            continue

        def _val(key: str) -> str:
            return str(raw.get(fmap[key], "") or "").strip()

        try:
            lat = float(_val("latitude"))
            lon = float(_val("longitude"))
            height = float(_val("height"))
        except ValueError:
            errors.append(f"line {i} ({station}): latitude, longitude and height must be numbers")
            continue

        if not (-90.0 <= lat <= 90.0):
            errors.append(f"line {i} ({station}): latitude {lat} out of range [-90, 90]")
            continue
        if not (-180.0 <= lon <= 180.0):
            errors.append(f"line {i} ({station}): longitude {lon} out of range [-180, 180]")
            continue

        source = _val("source") if "source" in fmap else ""
        if not source:
            source = _DEFAULT_SOURCE

        record = {"station": station, "latitude": lat, "longitude": lon,
                  "height": height, "source": source}
        if station in by_station:
            rows[by_station[station]] = record          # later duplicate wins
        else:
            by_station[station] = len(rows)
            rows.append(record)

        if len(errors) >= 50:
            break

    if errors:
        more = "\n… and more" if len(errors) >= 50 else ""
        raise ValueError("Validation failed:\n" + "\n".join(errors[:50]) + more)
    if not rows:
        raise ValueError("No valid coordinate rows found.")
    return rows


def _read_rows(path: pathlib.Path) -> list[dict]:
    """Read an existing (trusted) coordinates CSV into normalized rows, skipping
    any unparseable lines."""
    out: list[dict] = []
    with path.open(newline="") as fh:
        for row in csv.DictReader(fh):
            try:
                station = str(row.get("station", "") or "").strip().upper()
                if not station:
                    continue
                out.append({
                    "station": station,
                    "latitude": float(row["latitude"]),
                    "longitude": float(row["longitude"]),
                    "height": float(row["height"]),
                    "source": (str(row.get("source", "") or "").strip() or _DEFAULT_SOURCE),
                })
            except (KeyError, ValueError, TypeError):
                continue
    return out


def write_rows(rows: list[dict]) -> pathlib.Path:
    """Write *rows* to the editable data-dir CSV (atomic, sorted by station)."""
    dst = ensure_data_csv()
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(_HEADER)
    for r in sorted(rows, key=lambda r: r["station"]):
        writer.writerow([
            r["station"], _fmt(r["latitude"]), _fmt(r["longitude"]),
            _fmt(r["height"]), r["source"],
        ])
    tmp = dst.with_name(dst.name + ".tmp")
    tmp.write_text(buf.getvalue(), encoding="utf-8")
    tmp.replace(dst)
    _default_coords.cache_clear()
    return dst


def read_text() -> str:
    """Return the current editable coordinates CSV text (seeding first)."""
    return ensure_data_csv().read_text(encoding="utf-8")


def save_edited(text: str) -> int:
    """Validate *text* and replace the coordinates file with it (Edit Coordinates).
    Returns the number of rows written.  Raises ``ValueError`` if invalid."""
    rows = validate_and_normalize(text)
    write_rows(rows)
    return len(rows)


def merge_upload(text: str) -> tuple[int, int, int]:
    """Validate an uploaded CSV *text* and merge it into the existing file, with
    uploaded rows taking priority on station matches (Update Coordinates).

    Returns ``(total, added, updated)``.  Raises ``ValueError`` if invalid.
    """
    uploaded = validate_and_normalize(text)
    merged: dict[str, dict] = {r["station"]: r for r in _read_rows(ensure_data_csv())}
    added = updated = 0
    for r in uploaded:
        if r["station"] in merged:
            updated += 1
        else:
            added += 1
        merged[r["station"]] = r      # upload wins
    write_rows(list(merged.values()))
    return (len(merged), added, updated)

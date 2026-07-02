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
    c = coords["P143"]                            # same, raises KeyError if missing

    print(c.latitude, c.longitude, c.height, c.source)

    # Bulk lookup
    found = coords.lookup_all(["P143", "BEPK", "XXXX"])
    # found is dict[str, StationCoord | None]

The CSV is loaded once and cached in memory.  Pass a custom path to override
the default (reference/coordinates/coordinates.csv relative to the project root).
"""
from __future__ import annotations

import csv
import pathlib
from dataclasses import dataclass
from functools import lru_cache
from typing import Iterable


# Default path: <project_root>/resources/coordinates.csv
_DEFAULT_CSV = (
    pathlib.Path(__file__).resolve().parents[2]
    / "resources" / "coordinates.csv"
)


@dataclass(frozen=True, slots=True)
class StationCoord:
    site:      str
    latitude:  float
    longitude: float
    height:    float
    source:    str   # "gage" | "shakealert" | "rtdb"

    def __str__(self) -> str:
        return (f"{self.site}  lat={self.latitude:.6f}  lon={self.longitude:.6f}"
                f"  h={self.height:.3f} m  [{self.source}]")


class Coordinates:
    """In-memory coordinate table loaded from coordinates.csv."""

    def __init__(self, csv_path: pathlib.Path | str | None = None) -> None:
        path = pathlib.Path(csv_path) if csv_path is not None else _DEFAULT_CSV
        if not path.exists():
            raise FileNotFoundError(
                f"Coordinates file not found: {path}\n"
                "Run:  python resources/coordinates_generation/build_coordinates_csv.py  to regenerate it."
            )
        self._table: dict[str, StationCoord] = {}
        with path.open(newline="") as fh:
            for row in csv.DictReader(fh):
                site = row["site"].strip().upper()
                self._table[site] = StationCoord(
                    site=site,
                    latitude=float(row["latitude"]),
                    longitude=float(row["longitude"]),
                    height=float(row["height"]),
                    source=row["source"].strip(),
                )
        self._path = path

    # ------------------------------------------------------------------
    # Lookup API
    # ------------------------------------------------------------------

    def get(self, site: str) -> StationCoord | None:
        """Return the StationCoord for *site* (case-insensitive), or None."""
        return self._table.get(site.upper())

    def __getitem__(self, site: str) -> StationCoord:
        """Return the StationCoord for *site*, raising KeyError if absent."""
        try:
            return self._table[site.upper()]
        except KeyError:
            raise KeyError(f"Station not found: {site!r}") from None

    def __contains__(self, site: object) -> bool:
        return isinstance(site, str) and site.upper() in self._table

    def __len__(self) -> int:
        return len(self._table)

    def lookup_all(self, sites: Iterable[str]) -> dict[str, StationCoord | None]:
        """Look up multiple sites at once.  Returns dict with None for misses."""
        return {s: self._table.get(s.upper()) for s in sites}

    def all_sites(self) -> list[str]:
        """Sorted list of all known site codes."""
        return sorted(self._table)

    def __repr__(self) -> str:
        return f"Coordinates({len(self._table)} stations, source={self._path})"


# ---------------------------------------------------------------------------
# Module-level singleton (lazy-loaded)
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def _default_coords() -> Coordinates:
    return Coordinates()


def get(site: str) -> StationCoord | None:
    """Module-level shortcut: look up a station in the default Coordinates table."""
    return _default_coords().get(site)

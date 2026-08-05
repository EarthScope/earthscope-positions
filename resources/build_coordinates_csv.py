#!/usr/bin/env python3
"""
Merge three coordinate reference files into a single coordinates.csv.

Priority (highest → lowest):
  1. GAGE GPS IGS14 solutions      resources/coordinates_generation/gage_gps.igs14.txt
  2. ShakeAlert extended coords    resources/coordinates_generation/station_coords_extended.dat
  3. RealTimeDB                    resources/coordinates_generation/rtdb.csv

Any station appearing in a higher-priority source is kept and the lower-priority
entry is discarded.  The output has no duplicate stations.

Output: resources/coordinates.csv (the bundled template — see
  earthscope_positions.paths.ensure_resource for how it's seeded into the
  editable <data-directory>/resources/coordinates.csv copy)
  Columns: station, latitude, longitude, height, source
"""

from __future__ import annotations

import csv
import pathlib
import sys

RESOURCE = pathlib.Path(__file__).resolve().parents[0]
OUT = RESOURCE / "coordinates.csv"
COORD = RESOURCE / "coordinates_generation"


# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------


def parse_gage(path: pathlib.Path) -> list[dict]:
    """
    Format (comma-separated, after skipping # comments):
      ID, Station Name, Latitude (deg), Longitude (deg), Ellipsoidal Elevation (m),
      X (m), Y (m), Z (m), Epoch Date (YYYYMMDD)
    """
    rows = []
    with path.open() as fh:
        for raw in fh:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            parts = [p.strip() for p in line.split(",")]
            if len(parts) < 5:
                continue
            station = parts[0].upper()
            try:
                lat = float(parts[2])
                lon = float(parts[3])
                hgt = float(parts[4])
            except ValueError:
                continue
            rows.append(
                {
                    "station": station,
                    "latitude": lat,
                    "longitude": lon,
                    "height": hgt,
                    "source": "gage",
                }
            )
    return rows


def parse_shakealert(path: pathlib.Path) -> list[dict]:
    """
    Format (fixed whitespace-separated, after skipping # comments):
      Station  Lat  Lon  EllipElev  X  Y  Z  Epoch  Net  Status  ...
    Columns 0-3 are the ones we need.
    """
    rows = []
    with path.open() as fh:
        for raw in fh:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) < 4:
                continue
            station = parts[0].upper()
            try:
                lat = float(parts[1])
                lon = float(parts[2])
                hgt = float(parts[3])
            except ValueError:
                continue
            rows.append(
                {
                    "station": station,
                    "latitude": lat,
                    "longitude": lon,
                    "height": hgt,
                    "source": "shakealert",
                }
            )
    return rows


def parse_rtdb(path: pathlib.Path) -> list[dict]:
    """
    CSV with header: FourCharID, Lat, Long, Height
    """
    rows = []
    with path.open(newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            station = row["FourCharID"].strip().upper()
            try:
                lat = float(row["Lat"])
                lon = float(row["Long"])
                hgt = float(row["Height"])
            except (ValueError, KeyError):
                continue
            rows.append(
                {
                    "station": station,
                    "latitude": lat,
                    "longitude": lon,
                    "height": hgt,
                    "source": "rtdb",
                }
            )
    return rows


# ---------------------------------------------------------------------------
# Merge
# ---------------------------------------------------------------------------


def merge(sources: list[list[dict]]) -> list[dict]:
    """
    Apply priority-ordered merge: first occurrence of each station wins.
    Returns rows sorted by station name.
    """
    seen: dict[str, dict] = {}
    for source_rows in sources:
        for row in source_rows:
            station = row["station"]
            if station not in seen:
                seen[station] = row
    return sorted(seen.values(), key=lambda r: r["station"])


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    gage_path = COORD / "gage_gps.igs14.txt"
    shake_path = COORD / "station_coords_extended.dat"
    rtdb_path = COORD / "rtdb.csv"

    for p in (gage_path, shake_path, rtdb_path):
        if not p.exists():
            sys.exit(f"Missing source file: {p}")

    print(f"Reading GAGE …          {gage_path}")
    gage = parse_gage(gage_path)
    print(f"  {len(gage):5d} stations")

    print(f"Reading ShakeAlert …    {shake_path}")
    shake = parse_shakealert(shake_path)
    print(f"  {len(shake):5d} stations")

    print(f"Reading RTDB …          {rtdb_path}")
    rtdb = parse_rtdb(rtdb_path)
    print(f"  {len(rtdb):5d} stations")

    merged = merge([gage, shake, rtdb])

    src_counts: dict[str, int] = {}
    for row in merged:
        src_counts[row["source"]] = src_counts.get(row["source"], 0) + 1

    print(f"\nMerged: {len(merged)} unique stations")
    for src in ("gage", "shakealert", "rtdb"):
        print(f"  {src:12s}: {src_counts.get(src, 0):5d}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="") as fh:
        writer = csv.DictWriter(
            fh, fieldnames=["station", "latitude", "longitude", "height", "source"]
        )
        writer.writeheader()
        writer.writerows(merged)

    print(f"\nWrote {OUT}")


if __name__ == "__main__":
    main()

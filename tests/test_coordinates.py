"""Tests for the editable station-coordinates file: seeding, validation, merge
(upload wins), manual edit, the /api/coordinates endpoints, and that the map
payload includes coordinate-only (no-stream) stations."""
from __future__ import annotations

import pytest

from earthscope_positions import coordinates as C
from earthscope_positions import paths


def _write_data_csv(text: str) -> None:
    p = paths.coordinates_file()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


# ── seeding ───────────────────────────────────────────────────────────────────

def test_seeds_from_resources(project_tree):
    # No data-dir file yet → read_text() seeds it from bundled resources.
    assert not paths.coordinates_file().exists()
    text = C.read_text()
    assert paths.coordinates_file().exists()
    lines = text.splitlines()
    assert lines[0].split(",")[:4] == ["station", "latitude", "longitude", "height"]
    assert len(lines) > 100          # the bundled file has thousands of stations


# ── validation ────────────────────────────────────────────────────────────────

def test_source_defaults_to_user(project_tree):
    rows = C.validate_and_normalize("station,latitude,longitude,height\nABCD,40,-105,1600\n")
    assert rows == [{"station": "ABCD", "latitude": 40.0, "longitude": -105.0,
                     "height": 1600.0, "source": "user"}]


def test_columns_any_order_and_case(project_tree):
    rows = C.validate_and_normalize("Longitude,STATION,Height,Latitude\n-105,abcd,1600,40\n")
    assert rows[0]["station"] == "ABCD" and rows[0]["longitude"] == -105.0


def test_duplicate_station_last_wins(project_tree):
    rows = C.validate_and_normalize(
        "station,latitude,longitude,height\nX,1,2,3\nX,10,20,30\n"
    )
    assert len(rows) == 1 and rows[0]["latitude"] == 10.0


@pytest.mark.parametrize("bad,needle", [
    ("latitude,longitude,height\n1,2,3\n", "Missing required column"),
    ("station,latitude,longitude,height\nX,nan-ish,2,3\n", "must be numbers"),
    ("station,latitude,longitude,height\nX,99,2,3\n", "latitude"),
    ("station,latitude,longitude,height\nX,40,200,3\n", "longitude"),
    ("station,latitude,longitude,height\n", "No valid coordinate rows"),
])
def test_validation_errors(project_tree, bad, needle):
    with pytest.raises(ValueError) as ei:
        C.validate_and_normalize(bad)
    assert needle in str(ei.value)


# ── merge (upload wins) ───────────────────────────────────────────────────────

def test_merge_upload_priority(project_tree):
    _write_data_csv("station,latitude,longitude,height,source\n"
                    "AAAA,1,2,3,gage\nBBBB,4,5,6,rtdb\n")
    total, added, updated = C.merge_upload(
        "station,latitude,longitude,height\nBBBB,40,-105,99\nCCCC,10,20,30\n"
    )
    assert (total, added, updated) == (3, 1, 1)   # CCCC added, BBBB updated
    coords = C.Coordinates()
    assert coords.get("BBBB").latitude == 40.0       # upload won
    assert coords.get("BBBB").source == "user"       # source defaulted
    assert coords.get("AAAA").source == "gage"       # untouched
    assert coords.get("CCCC") is not None


def test_save_edited_replaces(project_tree):
    _write_data_csv("station,latitude,longitude,height,source\nOLD,1,2,3,gage\n")
    n = C.save_edited("station,latitude,longitude,height\nNEW,7,8,9\n")
    assert n == 1
    coords = C.Coordinates()
    assert coords.get("OLD") is None and coords.get("NEW") is not None


# ── endpoints ─────────────────────────────────────────────────────────────────

@pytest.fixture
def client(project_tree):
    from fastapi.testclient import TestClient
    import earthscope_positions.webserver.webserver as w
    return TestClient(w.app)


def test_endpoint_get_seeds_and_returns(client):
    r = client.get("/api/coordinates/raw")
    assert r.status_code == 200
    assert r.json()["content"].splitlines()[0].startswith("station,")


def test_endpoint_put_valid_and_invalid(client):
    ok = client.put("/api/coordinates/raw",
                    json={"content": "station,latitude,longitude,height\nZZZZ,12,34,56\n"})
    assert ok.status_code == 200 and ok.json()["count"] == 1
    bad = client.put("/api/coordinates/raw",
                     json={"content": "station,latitude,longitude,height\nZZZZ,999,34,56\n"})
    assert bad.status_code == 400 and "latitude" in bad.json()["error"]


def test_endpoint_update_merges(client):
    client.put("/api/coordinates/raw",
               json={"content": "station,latitude,longitude,height,source\nAAAA,1,2,3,gage\n"})
    r = client.post("/api/coordinates/update",
                    json={"content": "station,latitude,longitude,height\nBBBB,4,5,6\n"})
    assert r.status_code == 200
    body = r.json()
    assert body["added"] == 1 and body["total"] == 2


# ── map payload includes coordinate-only stations ─────────────────────────────

def test_stations_payload_filters_to_streams_and_all_stations_list(project_tree):
    import json
    import earthscope_positions.webserver.webserver as w

    # Coordinates for three stations: one with a stream, one only in the
    # all-stations list (no stream), and one that's coordinate-only (neither).
    _write_data_csv("station,latitude,longitude,height,source\n"
                    "P143,38.7,-119.7,2000,gage\n"
                    "KNOWN,45.0,-100.0,500,user\n"
                    "LONER,40.0,-90.0,300,user\n")
    station_lists = paths.station_lists_dir()
    station_lists.mkdir(parents=True, exist_ok=True)
    (station_lists / "all-stations.jsonl").write_text(
        json.dumps({"station": "P143"}) + "\n" + json.dumps({"station": "KNOWN"}) + "\n"
    )

    w._station_builder_coords = C.Coordinates()
    payload = w._stations_payload(["P143.NC.LY_.20"])
    by_station = {s["station"]: s for s in payload}

    # A station with a stream is included regardless of the all-stations list:
    assert by_station["P143"]["streams"] == ["P143.NC.LY_.20"]
    # A station in the all-stations list but with no stream is included, with
    # its coordinates attached:
    assert "KNOWN" in by_station
    assert by_station["KNOWN"]["streams"] == []
    assert by_station["KNOWN"]["lat"] == 45.0
    # A station that only exists in coordinates.csv (neither a stream nor in
    # the all-stations list) is excluded — coordinates.csv also holds
    # thousands of unrelated reference entries that shouldn't show up here.
    assert "LONER" not in by_station

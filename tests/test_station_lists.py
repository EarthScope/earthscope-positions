"""Tests for station (station-code) lists, the startup preload builders, the
network-stations helper, and subprocess data-dir propagation."""
from __future__ import annotations

import json

import pytest

from earthscope_positions import paths
from earthscope_positions.stations import station_list


# ── preload / station-list builders (with a faked discovery API) ──────────────

_STREAMS = [
    {"edid": "E1", "geosncl": "P143.NC.LY_.20"},
    {"edid": "E2", "geosncl": "P143.PB.LY_.30"},   # same station, different stream
    {"edid": "E3", "geosncl": "BEPK.CI.LY_.00"},
]


def test_preload_creates_all_four_lists(project_tree, fake_discover_api):
    fake_discover_api.stream_records = _STREAMS
    created = station_list.preload_default_lists()

    # stream-lists/ (streams) and station-lists/ (stations)
    all_streams = paths.stream_lists_dir() / "all-streams.jsonl"
    all_stations = paths.station_lists_dir() / "all-stations.jsonl"
    sa_streams  = paths.stream_lists_dir() / "shake-alert.jsonl"
    sa_stations = paths.station_lists_dir() / "shake-alert.jsonl"
    for p in (all_streams, all_stations, sa_streams, sa_stations):
        assert p.exists(), p

    # all-streams has 3 geosncl records; all-stations has 2 unique stations
    stream_recs = [json.loads(l) for l in all_streams.read_text().splitlines() if l.strip()]
    assert {r["geosncl"] for r in stream_recs} == {s["geosncl"] for s in _STREAMS}
    station_recs = [json.loads(l) for l in all_stations.read_text().splitlines() if l.strip()]
    assert {r["station"] for r in station_recs} == {"P143", "BEPK"}

    assert created["all-streams"] == 3 and created["all-stations"] == 2


def test_preload_is_idempotent(project_tree, fake_discover_api):
    fake_discover_api.stream_records = _STREAMS
    station_list.preload_default_lists()
    n_calls = len(fake_discover_api.stream_calls)
    again = station_list.preload_default_lists()
    assert again == {}                                  # nothing created
    assert len(fake_discover_api.stream_calls) == n_calls  # no new API calls


def test_network_stations(project_tree, fake_discover_api):
    fake_discover_api.stream_records = _STREAMS
    stations = station_list.network_stations("SHAKE:ShakeAlert")
    assert stations == ["BEPK", "P143"]
    assert fake_discover_api.stream_calls[-1]["network_name"] == "SHAKE:ShakeAlert"


def test_save_station_list_writes_stations(project_tree):
    p = station_list.save_station_list("my-stations", ["p143", "BEPK", "p143"])
    assert p == paths.station_lists_dir() / "my-stations.jsonl"
    recs = [json.loads(l) for l in p.read_text().splitlines() if l.strip()]
    assert {r["station"] for r in recs} == {"P143", "BEPK"}   # upper-cased, deduped


# ── /api/station-lists endpoints ──────────────────────────────────────────────

@pytest.fixture
def client(project_tree):
    from fastapi.testclient import TestClient
    import earthscope_positions.webserver.webserver as w
    return TestClient(w.app)


def test_station_list_crud(client):
    # create via raw save
    r = client.post("/api/station-lists/bay-area/raw",
                    json={"content": '{"station":"P143"}\n{"station":"BEPK"}\n'})
    assert r.status_code == 200
    # list + get
    assert "bay-area" in client.get("/api/station-lists").json()["lists"]
    got = client.get("/api/station-lists/bay-area").json()
    assert got["stations"] == ["BEPK", "P143"]
    # rename
    assert client.post("/api/station-lists/bay-area/rename", json={"new_name": "west"}).status_code == 200
    assert "west" in client.get("/api/station-lists").json()["lists"]
    # delete
    assert client.request("DELETE", "/api/station-lists/west").status_code == 200
    assert "west" not in client.get("/api/station-lists").json()["lists"]


def test_station_list_raw_rejects_bad_rows(client):
    bad = client.post("/api/station-lists/x/raw", json={"content": '{"nope":"P143"}\n'})
    assert bad.status_code == 400 and "station" in bad.json()["error"]


def test_save_station_list_structured(client):
    r = client.post("/api/station-lists/team", json={"stations": ["p1", "P2", "p1"]})
    assert r.status_code == 200 and r.json()["count"] == 2


# ── subprocess data-dir propagation ───────────────────────────────────────────

def test_child_env_propagates_data_dir(monkeypatch, tmp_path):
    from earthscope_positions.webserver import webserver as w
    paths.set_configured_data_dir(tmp_path)
    # There is no --data-directory flag any more; the server hands its resolved
    # directory to child processes through the environment instead.
    env = w._child_env()
    assert env[paths.ENV_VAR] == str(tmp_path.resolve())
    assert "PATH" in env, "must extend os.environ, not replace it"

# ---------------------------------------------------------------------------
# Loading a network leaves a saved station list behind
# ---------------------------------------------------------------------------

def test_network_station_list_creates_and_caches(project_tree, monkeypatch):
    """First load queries the API and saves; the second reads the file back."""
    calls = []

    def _fake_network_stations(network):
        calls.append(network)
        return ["P143", "BEPK"]

    monkeypatch.setattr(station_list, "network_stations", _fake_network_stations)

    name, stations, cached = station_list.network_station_list("SHAKE:ShakeAlert")
    assert name == "shake-shakealert"
    assert stations == ["BEPK", "P143"]
    assert cached is False
    assert (paths.station_lists_dir() / "shake-shakealert.jsonl").exists()
    assert calls == ["SHAKE:ShakeAlert"]

    name2, stations2, cached2 = station_list.network_station_list("SHAKE:ShakeAlert")
    assert (name2, stations2, cached2) == (name, stations, True)
    assert calls == ["SHAKE:ShakeAlert"], "cached load must not re-query the API"


def test_network_station_list_refresh_requeries(project_tree, monkeypatch):
    calls = []

    def _fake(network):
        calls.append(network)
        return ["P143"] if len(calls) == 1 else ["P143", "P157"]

    monkeypatch.setattr(station_list, "network_stations", _fake)
    station_list.network_station_list("RTDB:PBO")
    _, stations, cached = station_list.network_station_list("RTDB:PBO", refresh=True)
    assert cached is False
    assert stations == ["P143", "P157"]
    assert len(calls) == 2


def test_cached_load_preserves_hand_edits(project_tree, monkeypatch):
    """A user who edits the saved list must not have it silently overwritten."""
    monkeypatch.setattr(station_list, "network_stations", lambda n: ["P143", "P157"])
    name, _, _ = station_list.network_station_list("RTDB:PBO")
    station_list.save_station_list(name, ["P143"])          # user removes one
    _, stations, cached = station_list.network_station_list("RTDB:PBO")
    assert cached is True
    assert stations == ["P143"]


def test_read_station_list_skips_malformed_lines(project_tree):
    path = paths.station_lists_dir() / "messy.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{"station":"P143"}\nnot json\n\n{"station":"p157"}\n{"nope":1}\n')
    assert station_list.read_station_list("messy") == ["P143", "P157"]


def test_read_station_list_missing_is_empty(project_tree):
    assert station_list.read_station_list("nope") == []


def test_network_stations_endpoint_saves_and_reports(client, project_tree, monkeypatch):
    monkeypatch.setattr(station_list, "network_stations", lambda n: ["P143", "BEPK"])

    r = client.get("/api/station-builder/network-stations",
                   params={"network": "SHAKE:ShakeAlert"})
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "shake-shakealert"
    assert body["stations"] == ["BEPK", "P143"]
    assert body["cached"] is False

    # The saved list must now show up in the station-list listing.
    assert "shake-shakealert" in client.get("/api/station-lists").json()["lists"]

    again = client.get("/api/station-builder/network-stations",
                       params={"network": "SHAKE:ShakeAlert"}).json()
    assert again["cached"] is True

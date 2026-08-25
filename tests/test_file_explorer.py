"""/api/files — the File Explorer's listing, summaries and file management.

Rooted at the data directory (not <base>/plots as the old Plots tab was), so
the path-traversal guard matters more here than it did before.
"""
from __future__ import annotations

import io
import json

import pyarrow as pa
import pyarrow.ipc as ipc
import pytest

from conftest import POSITIONS_SCHEMA, make_positions_arrow
from earthscope_positions import paths


@pytest.fixture
def client(project_tree):
    from fastapi.testclient import TestClient
    import earthscope_positions.webserver.webserver as w
    return TestClient(w.app)


@pytest.fixture
def tree(project_tree):
    """One file of each interesting kind under the data directory."""
    base = paths.base_dir()
    g = "P143.NC.LY_.20"
    ad = base / "arrow" / g / "202601"
    ad.mkdir(parents=True, exist_ok=True)
    arrow = ad / f"{g}_20260115T000000Z_20260116T000000Z.arrow"
    arrow.write_bytes(make_positions_arrow(120, as_stream=True))

    sl = base / "stream-lists"
    sl.mkdir(parents=True, exist_ok=True)
    (sl / "demo.jsonl").write_text(
        '{"geosncl":"P143.PB.LY_.10","edid":"e1","facility":"earthscope"}\n'
        '{"geosncl":"P157.NC.LY_.20","edid":"e2","facility":"cwu"}\n')

    stl = base / "station-lists"
    stl.mkdir(parents=True, exist_ok=True)
    (stl / "sites.jsonl").write_text('{"station":"P143"}\n{"station":"P157"}\n')

    gj = base / "geojson"
    gj.mkdir(parents=True, exist_ok=True)
    (gj / "d.geojson.jsonl").write_text(
        '{"type":"Feature","properties":{"station":"P143","time":"2026-01-15T00:00:00Z"},'
        '"geometry":{"type":"Point","coordinates":[-124.3,40.2,10.0]}}\n')

    from earthscope_positions.export.miniseed_writer import load_spec, write_arrow_to_miniseed
    spec = load_spec(None)
    spec["root"] = str(base / "miniseed")
    written = write_arrow_to_miniseed(arrow, spec, verbose=False)

    return {
        "base": base,
        "arrow": str(arrow.relative_to(base)),
        "mseed": str(written[0].relative_to(base)),
        "stream_list": "stream-lists/demo.jsonl",
        "station_list": "station-lists/sites.jsonl",
        "geojson": "geojson/d.geojson.jsonl",
    }


def _rows(payload) -> dict:
    return {k: v for k, v in payload.get("rows", [])}


# ---------------------------------------------------------------------------
# Listing
# ---------------------------------------------------------------------------

def test_list_is_rooted_at_the_data_directory(client, tree):
    body = client.get("/api/files/list").json()
    assert body["root"] == str(tree["base"].resolve())
    names = {e["name"] for e in body["entries"]}
    assert {"arrow", "stream-lists", "station-lists"} <= names


def test_list_reports_kind_and_size(client, tree):
    entries = client.get("/api/files/list", params={"path": "stream-lists"}).json()["entries"]
    demo = next(e for e in entries if e["name"] == "demo.jsonl")
    assert demo["kind"] == "jsonl"
    assert demo["type"] == "file"
    assert demo["size"] > 0


@pytest.mark.parametrize("bad", [
    "../../../etc",
    "/etc/passwd",
    "../..",
    "arrow/../../..",
])
def test_traversal_outside_the_root_is_refused(client, tree, bad):
    assert client.get("/api/files/list", params={"path": bad}).status_code == 404


def test_sibling_directory_prefix_is_not_treated_as_inside(client, project_tree):
    """A plain string-prefix check would accept <base>-evil for a root of <base>."""
    evil = project_tree / f"{paths.base_dir().name}-evil"
    evil.mkdir(parents=True, exist_ok=True)
    (evil / "secret.jsonl").write_text('{"a":1}\n')
    assert client.get("/api/files/list", params={"path": f"../{evil.name}"}).status_code == 404


# ---------------------------------------------------------------------------
# Summaries
# ---------------------------------------------------------------------------

def test_arrow_summary(client, tree):
    body = client.get("/api/files/summary", params={"path": tree["arrow"]}).json()
    assert body["kind"] == "arrow"
    rows = _rows(body)
    assert rows["Rows"] == "120"
    assert "First sample" in rows and "Span" in rows
    assert {c["name"] for c in body["schema"]} >= {"time", "east", "north", "up"}


def test_miniseed_summary(client, tree):
    body = client.get("/api/files/summary", params={"path": tree["mseed"]}).json()
    assert body["kind"] == "miniseed"
    rows = _rows(body)
    assert rows["Samples"] == "120"
    assert "miniSEED 3" in rows["Format"]
    assert body["channels"] and body["channels"][0]["name"].startswith("FDSN:")


def test_geojson_summary(client, tree):
    body = client.get("/api/files/summary", params={"path": tree["geojson"]}).json()
    assert body["kind"] == "geojson"
    rows = _rows(body)
    assert rows["Features"] == "1"
    assert "Latitude range" in rows


def test_stream_list_summary_identifies_kind(client, tree):
    rows = _rows(client.get("/api/files/summary",
                            params={"path": tree["stream_list"]}).json())
    assert rows["Kind"] == "stream list"
    assert rows["Unique streams"] == "2"


def test_station_list_summary_identifies_kind(client, tree):
    rows = _rows(client.get("/api/files/summary",
                            params={"path": tree["station_list"]}).json())
    assert rows["Kind"] == "station list"
    assert rows["Unique stations"] == "2"


def test_unreadable_file_still_returns_a_manageable_payload(client, tree):
    """A corrupt file must stay renameable/deletable, so the summary degrades
    rather than 500ing."""
    bad = tree["base"] / "arrow" / "broken.arrow"
    bad.write_bytes(b"not an arrow file at all")
    body = client.get("/api/files/summary", params={"path": "arrow/broken.arrow"}).json()
    assert body["kind"] == "arrow"
    assert body["rows"] == []
    assert "error" in body


# ---------------------------------------------------------------------------
# Edit / rename / delete
# ---------------------------------------------------------------------------

def test_raw_round_trip(client, tree):
    body = client.get("/api/files/raw", params={"path": tree["station_list"]}).json()
    assert '{"station":"P143"}' in body["content"]

    new = '{"station":"P143"}\n{"station":"P157"}\n{"station":"P166"}\n'
    r = client.put("/api/files/raw", json={"path": tree["station_list"], "content": new})
    assert r.status_code == 200
    rows = _rows(client.get("/api/files/summary",
                            params={"path": tree["station_list"]}).json())
    assert rows["Unique stations"] == "3"


def test_saving_invalid_jsonl_is_rejected_and_file_untouched(client, tree):
    before = (tree["base"] / tree["station_list"]).read_text()
    r = client.put("/api/files/raw",
                   json={"path": tree["station_list"], "content": '{"station":"P143"}\nnope\n'})
    assert r.status_code == 400
    assert "line 2" in r.json()["error"]
    assert (tree["base"] / tree["station_list"]).read_text() == before


def test_binary_files_are_not_editable(client, tree):
    assert client.get("/api/files/raw", params={"path": tree["arrow"]}).status_code == 400
    body = client.get("/api/files/summary", params={"path": tree["arrow"]}).json()
    assert body["editable"] is False


def test_rename(client, tree):
    r = client.post("/api/files/rename",
                    json={"path": tree["station_list"], "name": "renamed.jsonl"})
    assert r.status_code == 200
    assert r.json()["path"] == "station-lists/renamed.jsonl"
    assert (tree["base"] / "station-lists" / "renamed.jsonl").exists()
    assert not (tree["base"] / tree["station_list"]).exists()


def test_rename_refuses_directory_components(client, tree):
    """A name with a path in it must not move the file elsewhere."""
    client.post("/api/files/rename",
                json={"path": tree["station_list"], "name": "../escaped.jsonl"})
    assert not (tree["base"].parent / "escaped.jsonl").exists()


def test_rename_refuses_existing_target(client, tree):
    (tree["base"] / "station-lists" / "taken.jsonl").write_text("{}\n")
    r = client.post("/api/files/rename",
                    json={"path": tree["station_list"], "name": "taken.jsonl"})
    assert r.status_code == 409
    assert (tree["base"] / tree["station_list"]).exists()


def test_delete_file(client, tree):
    assert client.delete("/api/files", params={"path": tree["station_list"]}).status_code == 200
    assert not (tree["base"] / tree["station_list"]).exists()


def test_delete_refuses_directories(client, tree):
    r = client.delete("/api/files", params={"path": "stream-lists"})
    assert r.status_code == 400
    assert (tree["base"] / "stream-lists").is_dir()


def test_delete_refuses_outside_the_root(client, tree):
    assert client.delete("/api/files", params={"path": "../../../etc/passwd"}).status_code == 404


# ---------------------------------------------------------------------------
# CSV / TOML summaries
# ---------------------------------------------------------------------------

@pytest.fixture
def csv_and_toml(project_tree):
    base = paths.base_dir()
    res = base / "resources"
    res.mkdir(parents=True, exist_ok=True)
    (res / "coords.csv").write_text(
        "station,latitude,longitude,height,source\n"
        "P143,36.5,-121.2,300.5,gage\n"
        "P157,40.2,-124.3,120.0,rtdb\n"
        "P166,,,,\n"
    )
    (res / "spec.toml").write_text(
        '# a comment\n'
        'root = "data/miniseed"\n'
        'extension = ".ms"\n'
        '\n[encoding]\n'
        'format_version = 3\n'
        'max_record_length = 4096\n'
    )
    (res / "broken.toml").write_text('this = is = not = toml\n')
    return base


def _cols(payload) -> dict:
    return {c["name"]: c for c in payload.get("columns", [])}


def test_csv_summary_shape_and_headers(client, csv_and_toml):
    body = client.get("/api/files/summary", params={"path": "resources/coords.csv"}).json()
    assert body["kind"] == "csv"
    rows = _rows(body)
    assert rows["Rows"] == "3"
    assert rows["Columns"] == "5"
    assert rows["Headers"] == "station, latitude, longitude, height, source"


def test_csv_numeric_columns_get_a_range(client, csv_and_toml):
    cols = _cols(client.get("/api/files/summary",
                            params={"path": "resources/coords.csv"}).json())
    assert "36.5" in cols["latitude"]["detail"] and "40.2" in cols["latitude"]["detail"]
    # A column with a blank cell must report it -- that is the point of the count.
    assert cols["latitude"]["blank"] == 1
    assert cols["latitude"]["filled"] == 2


def test_csv_categorical_columns_list_their_values(client, csv_and_toml):
    cols = _cols(client.get("/api/files/summary",
                            params={"path": "resources/coords.csv"}).json())
    assert "gage" in cols["source"]["detail"]
    assert "rtdb" in cols["source"]["detail"]


def test_csv_sample_includes_the_header(client, csv_and_toml):
    body = client.get("/api/files/summary", params={"path": "resources/coords.csv"}).json()
    assert body["sample"][0].startswith("station,latitude")


def test_empty_csv_does_not_error(client, csv_and_toml):
    (csv_and_toml / "resources" / "empty.csv").write_text("")
    body = client.get("/api/files/summary", params={"path": "resources/empty.csv"}).json()
    assert "error" not in body
    assert _rows(body)["Rows"] == "0"


def test_toml_summary_flattens_tables(client, csv_and_toml):
    body = client.get("/api/files/summary", params={"path": "resources/spec.toml"}).json()
    assert body["kind"] == "toml"
    rows = _rows(body)
    assert rows["Valid TOML"] == "yes"
    assert "[encoding]" in rows["Tables"]
    settings = {s["key"]: s["value"] for s in body["settings"]}
    assert settings["root"] == "data/miniseed"
    assert settings["encoding.format_version"] == "3"
    assert settings["encoding.max_record_length"] == "4096"


def test_toml_counts_comment_lines(client, csv_and_toml):
    rows = _rows(client.get("/api/files/summary",
                            params={"path": "resources/spec.toml"}).json())
    assert rows["Comment lines"] == "1"


def test_invalid_toml_reports_the_parse_error(client, csv_and_toml):
    """Someone opening a spec here is usually looking for exactly this."""
    rows = _rows(client.get("/api/files/summary",
                            params={"path": "resources/broken.toml"}).json())
    assert rows["Valid TOML"] == "no"
    assert "Parse error" in rows


@pytest.mark.parametrize("name", ["coords.csv", "spec.toml"])
def test_csv_and_toml_are_editable(client, csv_and_toml, name):
    body = client.get("/api/files/summary", params={"path": f"resources/{name}"}).json()
    assert body["editable"] is True
    raw = client.get("/api/files/raw", params={"path": f"resources/{name}"})
    assert raw.status_code == 200


# ---------------------------------------------------------------------------
# /api/config/data-directory — the Overview page's read-only config panel
# ---------------------------------------------------------------------------

def test_data_directory_config_reports_resolution(client, project_tree):
    body = client.get("/api/config/data-directory").json()
    assert body["data_directory"] == str(paths.base_dir())
    assert body["source"] == paths.base_dir_source()
    assert body["config_file"] == str(paths.config_path())
    assert body["env_var"] == paths.ENV_VAR
    names = {d["name"] for d in body["subdirectories"]}
    assert {"arrow", "stream-lists", "station-lists", "plots", "resources"} == names


def test_data_directory_config_flags_an_env_override(client, project_tree, monkeypatch, tmp_path):
    override = tmp_path / "elsewhere"
    override.mkdir()
    monkeypatch.setenv(paths.ENV_VAR, str(override))
    paths.reset_cache()
    body = client.get("/api/config/data-directory").json()
    assert body["source"] == "env"
    assert body["mismatch"] is True
    assert body["env_value"] == str(override)


def test_data_directory_config_is_read_only(client, project_tree):
    """Switching is a CLI operation; the endpoint must not accept writes."""
    for verb in ("post", "put", "delete"):
        r = getattr(client, verb)("/api/config/data-directory")
        assert r.status_code == 405, f"{verb.upper()} should not be allowed"


def test_server_config_endpoint_still_works(client, project_tree):
    """/api/config reports host/port — the data-directory panel must not shadow it."""
    body = client.get("/api/config").json()
    assert {"base_url", "hostname", "port"} <= set(body)


# ---------------------------------------------------------------------------
# Docker mount reporting
# ---------------------------------------------------------------------------

def test_config_reports_no_docker_by_default(client, project_tree, monkeypatch):
    monkeypatch.delenv("ES_POS_HOST_DATA_DIRECTORY", raising=False)
    body = client.get("/api/config/data-directory").json()
    assert body["host_data_directory"] is None


def test_config_reports_the_host_side_of_the_mount(client, project_tree, monkeypatch, tmp_path):
    """Inside a container the resolved path is the container path, which does
    not exist on the host — the UI needs both ends of the bind mount."""
    container = tmp_path / "container-data"
    container.mkdir()
    monkeypatch.setenv("ES_POS_HOST_DATA_DIRECTORY", "/Users/someone/earthscope-positions")
    monkeypatch.setenv(paths.ENV_VAR, str(container))
    paths.reset_cache()

    body = client.get("/api/config/data-directory").json()
    assert body["in_docker"] is True
    assert body["host_data_directory"] == "/Users/someone/earthscope-positions"
    assert body["data_directory"] == str(container)

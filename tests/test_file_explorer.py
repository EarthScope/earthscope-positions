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


# ---------------------------------------------------------------------------
# GeoJSON preview lines
# ---------------------------------------------------------------------------

def _ndjson_feature(i: int) -> str:
    return json.dumps({
        "type": "Feature",
        "properties": {"station": f"P{i:03d}", "time": f"2026-01-15T00:00:{i:02d}Z"},
        "geometry": {"type": "Point", "coordinates": [-124.0 - i / 1000, 40.0 + i / 1000, 10.0]},
    })


def test_geojson_preview_returns_25_lines(client, project_tree):
    d = paths.base_dir() / "geojson"
    d.mkdir(parents=True, exist_ok=True)
    (d / "big.geojson.jsonl").write_text(
        "\n".join(_ndjson_feature(i) for i in range(200)) + "\n")

    body = client.get("/api/files/summary", params={"path": "geojson/big.geojson.jsonl"}).json()
    assert body["kind"] == "geojson"
    assert len(body["sample"]) == 25
    assert body["sample_total"] == 200
    assert json.loads(body["sample"][0])["properties"]["station"] == "P000"
    assert json.loads(body["sample"][24])["properties"]["station"] == "P024"


def test_geojson_preview_of_a_short_file_returns_what_there_is(client, project_tree):
    d = paths.base_dir() / "geojson"
    d.mkdir(parents=True, exist_ok=True)
    (d / "small.geojson.jsonl").write_text(
        "\n".join(_ndjson_feature(i) for i in range(3)) + "\n")
    body = client.get("/api/files/summary", params={"path": "geojson/small.geojson.jsonl"}).json()
    assert len(body["sample"]) == 3
    assert body["sample_total"] == 3


def test_geojson_line_count_is_reported(client, project_tree):
    d = paths.base_dir() / "geojson"
    d.mkdir(parents=True, exist_ok=True)
    (d / "n.geojson.jsonl").write_text(
        "\n".join(_ndjson_feature(i) for i in range(40)) + "\n")
    rows = {k: v for k, v in
            client.get("/api/files/summary",
                       params={"path": "geojson/n.geojson.jsonl"}).json()["rows"]}
    assert rows["Lines"] == "40"


def test_single_line_featurecollection_is_truncated(client, project_tree):
    """A pretty-printed-on-one-line FeatureCollection can be megabytes; the
    preview must stay renderable rather than shipping the whole line."""
    d = paths.base_dir() / "geojson"
    d.mkdir(parents=True, exist_ok=True)
    doc = {"type": "FeatureCollection",
           "features": [json.loads(_ndjson_feature(i)) for i in range(2000)]}
    (d / "one-line.geojson").write_text(json.dumps(doc))

    body = client.get("/api/files/summary", params={"path": "geojson/one-line.geojson"}).json()
    assert len(body["sample"]) == 1
    assert len(body["sample"][0]) < 2200, "long line must be clipped"
    assert "chars)" in body["sample"][0], "clipping must say how long the line really is"
    assert {k: v for k, v in body["rows"]}["Features"] == "2,000"


# ---------------------------------------------------------------------------
# MiniSEED waveform plot
# ---------------------------------------------------------------------------

def test_miniseed_plot_returns_a_png(client, tree):
    r = client.get("/api/files/plot", params={"path": tree["mseed"]})
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"
    assert r.content.startswith(b"\x89PNG\r\n\x1a\n")
    assert len(r.content) > 1000


def test_plot_refuses_a_kind_it_cannot_render(client, tree):
    r = client.get("/api/files/plot", params={"path": tree["stream_list"]})
    assert r.status_code == 400
    assert "No plot for" in r.json()["error"]


def test_plot_refuses_traversal(client, tree):
    assert client.get("/api/files/plot",
                      params={"path": "../../../etc/passwd"}).status_code == 404


def test_plot_of_an_unreadable_file_errors_cleanly(client, tree):
    """A corrupt file must produce a handled error, not a 500 traceback that
    leaves the rest of the preview unusable."""
    bad = tree["base"] / "miniseed" / "broken.mseed"
    bad.parent.mkdir(parents=True, exist_ok=True)
    bad.write_bytes(b"definitely not miniseed")
    r = client.get("/api/files/plot", params={"path": "miniseed/broken.mseed"})
    assert r.status_code == 500
    assert "error" in r.json()


# ---------------------------------------------------------------------------
# Plot data preparation
# ---------------------------------------------------------------------------

def test_gaps_become_nan_breaks(tree):
    """Consecutive records that do not join must not be drawn as a straight
    line across the missing time."""
    import earthscope_positions.webserver.webserver as w
    series = w._mseed_series(tree["base"] / tree["mseed"])
    assert series
    entry = next(iter(series.values()))
    assert len(entry["v"]) >= 120


def test_minmax_decimation_preserves_extremes():
    """Plain striding would drop a one-sample spike; for a data-quality preview
    that is the one thing that must survive."""
    import earthscope_positions.webserver.webserver as w
    values = [0.0] * 10_000
    values[4321] = 999.0          # a lone spike
    values[8765] = -42.0
    times = list(range(len(values)))

    out_t, out_v = w._decimate_minmax(times, values, 400)
    assert len(out_v) <= 500
    assert max(out_v) == 999.0
    assert min(out_v) == -42.0


def test_decimation_is_a_noop_below_the_threshold():
    import earthscope_positions.webserver.webserver as w
    times, values = list(range(50)), [float(i) for i in range(50)]
    assert w._decimate_minmax(times, values, 4000) == (times, values)


def test_decimation_keeps_time_order():
    import earthscope_positions.webserver.webserver as w
    values = [float((i * 37) % 101) for i in range(20_000)]
    out_t, _ = w._decimate_minmax(list(range(len(values))), values, 1000)
    assert out_t == sorted(out_t)


# ---------------------------------------------------------------------------
# Arrow / GeoJSON plots
# ---------------------------------------------------------------------------

def test_arrow_plot_returns_a_png(client, tree):
    r = client.get("/api/files/plot", params={"path": tree["arrow"]})
    assert r.status_code == 200
    assert r.content.startswith(b"\x89PNG\r\n\x1a\n")


def test_arrow_series_covers_every_numeric_column_but_time(client, tree):
    import earthscope_positions.webserver.webserver as w
    series = w._arrow_series(tree["base"] / tree["arrow"])
    assert "time" not in series
    assert {"east", "north", "up", "sigEE", "sigNN", "sigUU",
            "qChannel", "ingestLatency", "processingDelay"} <= set(series)
    assert len(series["east"]["t"]) == len(series["east"]["v"]) == 120


@pytest.mark.parametrize("name,expected", [
    ("x.completeness.arrow", "completeness"),
    ("x_ppsd.arrow", "ppsd"),
    ("P143.NC.LY_.20_20260115T000000Z_20260116T000000Z.arrow", "positions"),
])
def test_arrow_shape_is_classified(name, expected):
    """Three different shapes hide behind one extension: positions and
    completeness are time series on different time columns, PPSD is a 2D
    period/power histogram and not a time series at all."""
    import pathlib as _pathlib
    import earthscope_positions.webserver.webserver as w
    assert w._arrow_plot_kind(_pathlib.Path(name)) == expected


def test_completeness_plot_uses_the_bucket_time_column(client, tree):
    """Completeness has no `time` column — it is bucketed on bucket_start_ms."""
    import pyarrow as pa
    import pyarrow.ipc as ipc
    import earthscope_positions.webserver.webserver as w

    n = 8
    table = pa.table({
        "bucket_start_ms": [1787443200000 + i * 900_000 for i in range(n)],
        "row_count": [900, 900, 867, 900, 900, 900, 900, 900],
        "expected_count": [900] * n,
        "completeness": [1.0, 1.0, 0.963, 1.0, 1.0, 1.0, 1.0, 1.0],
        "mean_ingest_latency_s": [0.21 + i * 0.01 for i in range(n)],
        "mean_processing_delay_s": [0.038] * n,
    })
    path = tree["base"] / "arrow" / "c.completeness.arrow"
    path.parent.mkdir(parents=True, exist_ok=True)
    with ipc.new_stream(path, table.schema) as wtr:
        wtr.write_table(table)

    series = w._arrow_series(path)
    assert "bucket_start_ms" not in series, "the time column is the axis, not a panel"
    assert {"completeness", "row_count", "expected_count",
            "mean_ingest_latency_s", "mean_processing_delay_s"} == set(series)
    assert len(series["completeness"]["v"]) == n

    r = client.get("/api/files/plot", params={"path": "arrow/c.completeness.arrow"})
    assert r.status_code == 200
    assert r.content.startswith(b"\x89PNG\r\n\x1a\n")


def test_completeness_panels_lead_with_the_ratio():
    import earthscope_positions.webserver.webserver as w
    keys = w._ordered_keys({"row_count", "expected_count", "completeness",
                            "mean_ingest_latency_s", "mean_processing_delay_s"})
    assert keys[0] == "completeness"
    assert keys[1:3] == ["row_count", "expected_count"]


def test_completeness_is_pinned_to_a_unit_range():
    """A healthy flat line at 1.0 must read as 'complete', not be autoscaled
    into a noisy hairline."""
    import earthscope_positions.webserver.webserver as w
    assert "completeness" in w._UNIT_RANGE_COLUMNS


def test_every_arrow_shape_reports_plottable(client, tree):
    for name in ("x.completeness.arrow", "x_ppsd.arrow"):
        derived = tree["base"] / "arrow" / name
        derived.parent.mkdir(parents=True, exist_ok=True)
        derived.write_bytes((tree["base"] / tree["arrow"]).read_bytes())
        body = client.get("/api/files/summary", params={"path": f"arrow/{name}"}).json()
        assert body["plottable"] is True, name


def test_plottable_flag_is_set_for_real_data(client, tree):
    for key in ("arrow", "mseed", "geojson"):
        body = client.get("/api/files/summary", params={"path": tree[key]}).json()
        assert body["plottable"] is True, key


def test_geojson_plot_returns_a_png(client, tree):
    r = client.get("/api/files/plot", params={"path": tree["geojson"]})
    assert r.status_code == 200
    assert r.content.startswith(b"\x89PNG\r\n\x1a\n")


def test_compact_geojson_series_flattens_coor_and_err(client, tree):
    import earthscope_positions.webserver.webserver as w
    path = tree["base"] / "geojson" / "compact.geojson.jsonl"
    path.write_text("\n".join(json.dumps({
        "time": 1787529600000 + i * 1000, "Q": 2, "type": "ENU",
        "SNCL": "X.Y.LY_.00", "coor": [0.01 * i, -0.02 * i, 0.03 * i],
        "err": [0.03, 0.04, 0.08], "rate": 1,
    }) for i in range(5)))
    series = w._geojson_series(path)
    assert {"East", "North", "Up", "East uncertainty", "North uncertainty",
            "Up uncertainty", "Quality"} <= set(series)
    assert series["East"]["v"][1] == pytest.approx(0.01)
    assert series["Up"]["v"][2] == pytest.approx(0.06)


def test_full_geojson_series_reads_geometry_and_properties(client, tree):
    """The two export shapes must flatten to the same columns, so the same data
    plots identically whichever format it was written in."""
    import earthscope_positions.webserver.webserver as w
    path = tree["base"] / "geojson" / "full.geojson.jsonl"
    path.write_text("\n".join(json.dumps({
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [0.01 * i, -0.02 * i, 0.03 * i]},
        "properties": {"coordinateType": "ENU", "SNCL": "X.Y.LY_.00",
                       "time": 1787529600000 + i * 1000,
                       "EError": 0.03, "NError": 0.04, "UError": 0.08,
                       "quality": 2, "sampleRate": 1},
    }) for i in range(5)))
    series = w._geojson_series(path)
    assert {"East", "North", "Up", "East uncertainty", "Quality"} <= set(series)
    assert series["East"]["v"][1] == pytest.approx(0.01)


def test_panel_order_puts_enu_first():
    import earthscope_positions.webserver.webserver as w
    keys = w._ordered_keys({"processingDelay", "up", "east", "north", "zzz"})
    assert keys[:3] == ["east", "north", "up"]
    assert keys[-1] == "zzz", "unknown columns sort after the known ones"


def test_null_samples_become_gaps_not_interpolation(client, tree):
    """A null in the Arrow file must break the line, not be closed over."""
    import math
    import pyarrow as pa
    import pyarrow.ipc as ipc
    import earthscope_positions.webserver.webserver as w
    from conftest import POSITIONS_SCHEMA

    n = 6
    table = pa.table({
        "time": [1787529600000 + i * 1000 for i in range(n)],
        "east": [0.0, 1.0, None, 3.0, 4.0, 5.0],
        "north": [0.0] * n, "up": [0.0] * n,
        "sigEE": [0.01] * n, "sigNN": [0.01] * n, "sigUU": [0.02] * n,
        "qChannel": [0] * n, "ingestLatency": [1] * n, "processingDelay": [1] * n,
    }, schema=POSITIONS_SCHEMA)
    path = tree["base"] / "arrow" / "gappy.arrow"
    with ipc.new_stream(path, table.schema) as wtr:
        wtr.write_table(table)

    series = w._arrow_series(path)
    assert math.isnan(series["east"]["v"][2])


@pytest.mark.parametrize("value,expected_ns", [
    (1787529600000, 1787529600000 * 1e6),          # epoch ms, as the exporters write
    ("1787529600000", 1787529600000 * 1e6),        # numeric string
    ("2026-01-15T00:00:00Z", 1768435200 * 1e9),    # ISO with Z
    ("2026-01-15T00:00:00+00:00", 1768435200 * 1e9),
    (None, None),
    ("", None),
    ("not a time", None),
    (True, None),                                   # bool is an int subclass
])
def test_feature_time_parsing(value, expected_ns):
    """Exports use epoch ms, but hand-written GeoJSON often carries ISO-8601;
    one such record must not fail the whole plot."""
    import earthscope_positions.webserver.webserver as w
    got = w._feature_time_ns(value)
    if expected_ns is None:
        assert got is None
    else:
        assert got == pytest.approx(expected_ns)


def test_geojson_values_are_capped_at_millimetres(project_tree):
    """Positions and errors are metres; 3 decimals is mm, the finest that is
    meaningful. Raw float64 leaks binary noise (0.037 -> 0.037000000000000005)
    into the JSON, which is not extra precision."""
    from earthscope_positions.export import geojson_writer as gw
    r = gw._make_rounder(None)
    assert r(0.037000000000000005) == 0.037
    assert r(0.0037500000000000003) == 0.004
    assert r(-0.075010000000001) == -0.075
    assert r(None) is None


def test_configured_precision_beyond_mm_is_capped(project_tree, capsys):
    from earthscope_positions.export import geojson_writer as gw
    gw._warned_precision = False
    r = gw._make_rounder(6)
    assert r(0.0375123456) == 0.038
    assert "capped" in capsys.readouterr().err


def test_coarser_precision_is_honoured(project_tree):
    """The cap is a maximum, not a fixed value — asking for less still works."""
    from earthscope_positions.export import geojson_writer as gw
    assert gw._make_rounder(2)(0.0375123456) == 0.04


def test_exported_geojson_has_no_long_floats(project_tree):
    """End-to-end: the bytes actually written must be clean."""
    import json as _json
    from earthscope_positions.export import geojson_writer as gw

    gsdir = paths.arrow_dir() / "P143.NC.LY_.20" / "202601"
    gsdir.mkdir(parents=True, exist_ok=True)
    ap = gsdir / "P143.NC.LY_.20_20260115T000000Z_20260116T000000Z.arrow"
    ap.write_bytes(make_positions_arrow(40, as_stream=True))

    for out in gw.write_arrow_to_geojson(ap, gw.load_spec(None), verbose=False):
        for line in out.read_text().splitlines():
            rec = _json.loads(line)
            props = rec.get("properties", {})
            values = list(rec.get("coor") or (rec.get("geometry") or {}).get("coordinates") or [])
            values += list(rec.get("err") or [])
            values += [props[k] for k in ("EError", "NError", "UError") if k in props]
            for v in values:
                if isinstance(v, float):
                    assert round(v, 3) == v, f"{v} in {out.name} exceeds mm precision"

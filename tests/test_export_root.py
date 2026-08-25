"""Export path-spec roots resolve against the data directory, not the CWD.

A relative root used to be resolved against the working directory. Inside a
container (WORKDIR /app, data mounted at /data) that silently wrote every
export to /app/data/... — the image's own filesystem — so the files existed,
were reported as written, and vanished when the container stopped.
"""
from __future__ import annotations

import pathlib

import pytest

from conftest import make_positions_arrow
from earthscope_positions import paths
from earthscope_positions.export import geojson_writer as gw
from earthscope_positions.export import miniseed_writer as mw

GEOSNCL = "P143.NC.LY_.20"


# ---------------------------------------------------------------------------
# resolve_export_root
# ---------------------------------------------------------------------------

def test_relative_root_anchors_to_the_data_directory(project_tree):
    assert paths.resolve_export_root("miniseed") == paths.base_dir() / "miniseed"


def test_relative_root_ignores_the_cwd(project_tree, tmp_path, monkeypatch):
    """The whole bug: standing somewhere else must not move the output."""
    elsewhere = tmp_path / "somewhere-else"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    resolved = paths.resolve_export_root("miniseed")
    assert resolved == paths.base_dir() / "miniseed"
    assert elsewhere not in resolved.parents


def test_legacy_data_prefix_is_stripped(project_tree):
    """Specs written before the move say "data/miniseed", from when the data
    directory *was* ./data. Anchoring that verbatim would nest it twice."""
    assert paths.resolve_export_root("data/miniseed") == paths.base_dir() / "miniseed"
    assert paths.resolve_export_root("data/geojson/full") == \
        paths.base_dir() / "geojson" / "full"


def test_absolute_root_is_left_alone(project_tree):
    assert paths.resolve_export_root("/archive/mseed") == pathlib.Path("/archive/mseed")


def test_user_home_is_expanded(project_tree):
    assert paths.resolve_export_root("~/exports") == pathlib.Path.home() / "exports"


def test_only_a_leading_data_segment_is_stripped(project_tree):
    """A directory legitimately called "data" deeper in the path must survive."""
    assert paths.resolve_export_root("mseed/data") == paths.base_dir() / "mseed" / "data"


# ---------------------------------------------------------------------------
# Writers honour it
# ---------------------------------------------------------------------------

@pytest.fixture
def arrow_file(project_tree):
    gsdir = paths.arrow_dir() / GEOSNCL / "202601"
    gsdir.mkdir(parents=True, exist_ok=True)
    ap = gsdir / f"{GEOSNCL}_20260115T000000Z_20260116T000000Z.arrow"
    ap.write_bytes(make_positions_arrow(20, as_stream=True))
    return ap


def test_miniseed_writes_under_the_data_directory(arrow_file, tmp_path, monkeypatch):
    elsewhere = tmp_path / "cwd-decoy"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)

    written = mw.write_arrow_to_miniseed(arrow_file, mw.load_spec(None), verbose=False)
    assert written
    for out in written:
        assert out.is_absolute()
        assert paths.base_dir() in out.parents
    assert not any(elsewhere.rglob("*.ms")), "nothing may land beside the CWD"


def test_miniseed_default_root_is_data_dir_relative():
    assert mw._SPEC_DEFAULTS["root"] == "miniseed"


def test_geojson_default_roots_are_data_dir_relative():
    spec = gw.load_spec(None)
    assert spec["compact"]["root"] == "geojson/compact"
    assert spec["full"]["root"] == "geojson/full"


def test_bundled_specs_have_no_legacy_data_prefix():
    """The shipped templates seed every new install, so they must be current."""
    bundled = paths.bundled_resources_dir()
    for name in ("miniseed_path_spec.toml", "geojson_path_spec.toml"):
        text = (bundled / name).read_text()
        assert 'root = "data/' not in text and 'root      = "data/' not in text


def test_absolute_root_override_still_works(arrow_file, tmp_path):
    """--root /archive/... must escape the data directory entirely."""
    spec = mw.load_spec(None)
    spec["root"] = str(tmp_path / "archive")
    written = mw.write_arrow_to_miniseed(arrow_file, spec, verbose=False)
    assert written
    for out in written:
        assert (tmp_path / "archive") in out.parents


def test_expected_out_paths_agree_with_what_is_written(arrow_file):
    """The --force skip check must resolve roots the same way the writer does,
    or re-runs would never detect existing output."""
    spec = mw.load_spec(None)
    predicted = mw.expected_out_paths(arrow_file, spec)
    written = mw.write_arrow_to_miniseed(arrow_file, spec, verbose=False)
    assert sorted(predicted) == sorted(written)


def test_verbose_output_prints_absolute_paths(arrow_file, capsys):
    """A CWD-relative display is what masked the bug — 'data/miniseed/...'
    looked local while the file was really inside the container."""
    mw.write_arrow_to_miniseed(arrow_file, mw.load_spec(None), verbose=True)
    for line in capsys.readouterr().out.splitlines():
        if ".ms" in line:
            assert " /" in line, f"path is not absolute: {line}"

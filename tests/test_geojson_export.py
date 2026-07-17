"""Tests for the Arrow→GeoJSON export writer: both formats are JSONL and use the
`.compact.geojson.jsonl` / `.full.geojson.jsonl` naming."""
from __future__ import annotations

import json
import os
import pathlib

import pytest

from conftest import make_positions_arrow
from earthscope_positions.export import geojson_writer as gw

GEOSNCL = "P143.NC.LY_.20"


@pytest.fixture
def arrow_in_tree(tmp_path, monkeypatch) -> pathlib.Path:
    monkeypatch.chdir(tmp_path)
    gsdir = tmp_path / GEOSNCL / "202601"
    gsdir.mkdir(parents=True)
    ap = gsdir / f"{GEOSNCL}_20260115T000000Z_20260116T000000Z.arrow"
    ap.write_bytes(make_positions_arrow(5, as_stream=True))
    return ap


def test_extensions_are_geojson_jsonl(arrow_in_tree):
    spec = gw.load_spec(None)
    assert spec["compact"]["extension"] == ".compact.geojson.jsonl"
    assert spec["full"]["extension"] == ".full.geojson.jsonl"
    names = [p.name for p in gw.expected_out_paths(arrow_in_tree, spec)]
    assert names == [
        f"{GEOSNCL}.2026.015.compact.geojson.jsonl",
        f"{GEOSNCL}.2026.015.full.geojson.jsonl",
    ]


def test_compact_is_jsonl(arrow_in_tree):
    spec = gw.load_spec(None)
    out = gw.write_arrow_to_compact_json(arrow_in_tree, spec, verbose=False)
    assert out.name.endswith(".compact.geojson.jsonl")
    lines = out.read_text().splitlines()
    assert len(lines) == 5
    rec = json.loads(lines[0])
    assert rec["SNCL"] == GEOSNCL and rec["type"] == "ENU" and "coor" in rec


def test_full_is_jsonl_of_features(arrow_in_tree):
    spec = gw.load_spec(None)
    out = gw.write_arrow_to_full_geojson(arrow_in_tree, spec, verbose=False)
    assert out.name.endswith(".full.geojson.jsonl")
    lines = out.read_text().splitlines()
    assert len(lines) == 5                     # one Feature per line, not one FeatureCollection
    for ln in lines:                           # every line is standalone valid JSON
        feat = json.loads(ln)
        assert feat["type"] == "Feature"
        assert feat["geometry"]["type"] == "Point"
        props = feat["properties"]
        assert props["SNCL"] == GEOSNCL        # SNCL + sampleRate embedded per feature
        assert "sampleRate" in props and props["coordinateType"] == "ENU"

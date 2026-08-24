"""Tests for the Arrow→MiniSEED export writer.

Record packing is done by `pymseed`/libmseed, so these tests are about the
things this repo is actually responsible for: channel→source-ID mapping, the
path spec, gap splitting, and the format-version selection.  Every assertion
reads the output back with pymseed rather than inspecting bytes by hand.
"""
from __future__ import annotations

import datetime as dt
import io
import pathlib

import pyarrow as pa
import pyarrow.ipc as ipc
import pytest
from pymseed import DataEncoding, MS3Record

from conftest import POSITIONS_SCHEMA, make_positions_arrow
from earthscope_positions.export import miniseed_writer as mw

GEOSNCL = "P143.NC.LY_.20"


def _read_records(path: pathlib.Path) -> list[dict]:
    """Read every record, copying out the fields we assert on.

    The reader reuses one record object per iteration, so the fields must be
    pulled inside the loop -- holding on to the MS3Record yields stale values.
    """
    out = []
    for rec in MS3Record.from_file(str(path), unpack_data=True):
        out.append({
            "sourceid":      rec.sourceid,
            "samplecnt":     rec.samplecnt,
            "starttime":     rec.starttime,
            "encoding":      rec.encoding,
            "formatversion": rec.formatversion,
            "reclen":        rec.reclen,
            "samprate":      rec.samprate,
            "data":          list(rec.datasamples),
        })
    return out


@pytest.fixture
def arrow_in_tree(tmp_path, monkeypatch) -> pathlib.Path:
    monkeypatch.chdir(tmp_path)
    gsdir = tmp_path / GEOSNCL / "202601"
    gsdir.mkdir(parents=True)
    ap = gsdir / f"{GEOSNCL}_20260115T000000Z_20260116T000000Z.arrow"
    ap.write_bytes(make_positions_arrow(10, as_stream=True))
    return ap


# ---------------------------------------------------------------------------
# Source identifiers / path spec
# ---------------------------------------------------------------------------

def test_parse_geosncl():
    gsid = mw.parse_geosncl(GEOSNCL)
    assert (gsid.station, gsid.network, gsid.band, gsid.source, gsid.location) \
        == ("P143", "NC", "L", "Y", "20")


@pytest.mark.parametrize("bad", ["P143.NC.LY_", "P143.NC.LYE.20", "nope"])
def test_parse_geosncl_rejects_junk(bad):
    with pytest.raises(ValueError):
        mw.parse_geosncl(bad)


def test_writes_one_file_per_channel(arrow_in_tree):
    spec = mw.load_spec(None)
    written = mw.write_arrow_to_miniseed(arrow_in_tree, spec, verbose=False)
    assert len(written) == len(mw.CHANNELS) == 8
    assert {p.name.split(".")[3] for p in written} == {
        f"LY{s}" for s in mw.CHANNELS
    }


def test_expected_out_paths_matches_what_is_written(arrow_in_tree):
    """The --force skip check predicts paths from the filename alone; if it
    drifts from the writer, exports silently stop being re-runnable."""
    spec = mw.load_spec(None)
    predicted = mw.expected_out_paths(arrow_in_tree, spec)
    written = mw.write_arrow_to_miniseed(arrow_in_tree, spec, verbose=False)
    assert sorted(predicted) == sorted(written)


# ---------------------------------------------------------------------------
# Format version
# ---------------------------------------------------------------------------

def test_defaults_to_version_3(arrow_in_tree):
    spec = mw.load_spec(None)
    assert spec["encoding"]["format_version"] == mw.DEFAULT_FORMAT_VERSION == 3
    written = mw.write_arrow_to_miniseed(arrow_in_tree, spec, verbose=False)
    for rec in _read_records(written[0]):
        assert rec["formatversion"] == 3


@pytest.mark.parametrize("version", [2, 3])
def test_both_versions_round_trip(arrow_in_tree, version):
    spec = mw.load_spec(None)
    written = mw.write_arrow_to_miniseed(
        arrow_in_tree, spec, format_version=version, verbose=False,
    )
    east = next(p for p in written if p.name.split(".")[3] == "LYE")
    recs = _read_records(east)
    assert recs, "no records written"
    assert all(r["formatversion"] == version for r in recs)
    assert sum(r["samplecnt"] for r in recs) == 10
    assert all(r["encoding"] == DataEncoding.FLOAT64 for r in recs)
    # east column is 0.001 * i for i in range(10)
    data = [v for r in recs for v in r["data"]]
    assert data == pytest.approx([0.001 * i for i in range(10)])


def test_version_2_maps_to_seed_codes(arrow_in_tree):
    """MiniSEED 2 has no source IDs; libmseed must round-trip ours through
    classic NET/STA/LOC/CHAN without mangling them."""
    spec = mw.load_spec(None)
    written = mw.write_arrow_to_miniseed(
        arrow_in_tree, spec, format_version=2, verbose=False,
    )
    east = next(p for p in written if p.name.split(".")[3] == "LYE")
    assert _read_records(east)[0]["sourceid"] == "FDSN:NC_P143_20_L_Y_E"


def test_spec_format_version_is_honoured(arrow_in_tree, tmp_path):
    spec = mw.load_spec(None)
    spec["encoding"]["format_version"] = 2
    written = mw.write_arrow_to_miniseed(arrow_in_tree, spec, verbose=False)
    assert _read_records(written[0])[0]["formatversion"] == 2


def test_explicit_version_overrides_spec(arrow_in_tree):
    spec = mw.load_spec(None)
    spec["encoding"]["format_version"] = 2
    written = mw.write_arrow_to_miniseed(
        arrow_in_tree, spec, format_version=3, verbose=False,
    )
    assert _read_records(written[0])[0]["formatversion"] == 3


def test_rejects_unknown_version(arrow_in_tree):
    spec = mw.load_spec(None)
    with pytest.raises(ValueError, match="Unsupported MiniSEED format version"):
        mw.write_arrow_to_miniseed(arrow_in_tree, spec, format_version=4, verbose=False)


# ---------------------------------------------------------------------------
# Record length
# ---------------------------------------------------------------------------

def test_version_2_rejects_non_power_of_two_record_length(arrow_in_tree):
    """Caught before writing, naming the spec key -- libmseed's own error
    surfaces mid-write and doesn't say which setting is at fault."""
    spec = mw.load_spec(None)
    spec["encoding"]["max_record_length"] = 3000
    with pytest.raises(ValueError, match="power of two"):
        mw.write_arrow_to_miniseed(arrow_in_tree, spec, format_version=2, verbose=False)


def test_version_3_allows_non_power_of_two_record_length(arrow_in_tree):
    spec = mw.load_spec(None)
    spec["encoding"]["max_record_length"] = 3000
    written = mw.write_arrow_to_miniseed(arrow_in_tree, spec, format_version=3, verbose=False)
    assert written


def test_record_length_bounds(arrow_in_tree):
    spec = mw.load_spec(None)
    spec["encoding"]["max_record_length"] = 64
    with pytest.raises(ValueError, match="between 128 and 65536"):
        mw.write_arrow_to_miniseed(arrow_in_tree, spec, verbose=False)


def test_small_record_length_splits_into_more_records(tmp_path, monkeypatch):
    """max_record_length is a byte budget: 512-byte records hold far fewer
    float64 samples than 4096-byte ones."""
    monkeypatch.chdir(tmp_path)
    gsdir = tmp_path / GEOSNCL / "202601"
    gsdir.mkdir(parents=True)
    ap = gsdir / f"{GEOSNCL}_20260115T000000Z_20260116T000000Z.arrow"
    ap.write_bytes(make_positions_arrow(400, as_stream=True))

    counts = {}
    for reclen in (512, 4096):
        spec = mw.load_spec(None)
        spec["encoding"]["max_record_length"] = reclen
        spec["root"] = f"out{reclen}"
        written = mw.write_arrow_to_miniseed(ap, spec, verbose=False)
        east = next(p for p in written if p.name.split(".")[3] == "LYE")
        recs = _read_records(east)
        counts[reclen] = len(recs)
        assert sum(r["samplecnt"] for r in recs) == 400
        assert all(r["reclen"] <= reclen for r in recs)
    assert counts[512] > counts[4096]


# ---------------------------------------------------------------------------
# Gap handling
# ---------------------------------------------------------------------------

def test_split_on_gaps_breaks_on_time_jump_and_null():
    times = [0, 1000, 2000, 5000, 6000]
    values = [1.0, 2.0, None, 4.0, 5.0]
    segs = mw.split_on_gaps(times, values, expected_ms=1000.0, gap_factor=1.5)
    assert [v for _, v in segs] == [[1.0, 2.0], [4.0, 5.0]]


def test_time_gap_produces_separate_records(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    gsdir = tmp_path / GEOSNCL / "202601"
    gsdir.mkdir(parents=True)

    base = int(dt.datetime(2026, 1, 15, tzinfo=dt.timezone.utc).timestamp() * 1000)
    # 5 samples, a 1-minute hole, then 5 more.
    times = [base + i * 1000 for i in range(5)] + [base + 60_000 + i * 1000 for i in range(5)]
    n = len(times)
    table = pa.table(
        {
            "time": times,
            "east": [float(i) for i in range(n)],
            "north": [0.0] * n,
            "up": [0.0] * n,
            "sigEE": [0.01] * n,
            "sigNN": [0.01] * n,
            "sigUU": [0.02] * n,
            "qChannel": [0] * n,
            "ingestLatency": [1500] * n,
            "processingDelay": [200] * n,
        },
        schema=POSITIONS_SCHEMA,
    )
    sink = io.BytesIO()
    with ipc.new_stream(sink, table.schema) as w:
        w.write_table(table)
    ap = gsdir / f"{GEOSNCL}_20260115T000000Z_20260116T000000Z.arrow"
    ap.write_bytes(sink.getvalue())

    spec = mw.load_spec(None)
    written = mw.write_arrow_to_miniseed(ap, spec, verbose=False)
    east = next(p for p in written if p.name.split(".")[3] == "LYE")
    recs = _read_records(east)
    assert len(recs) == 2
    assert [r["samplecnt"] for r in recs] == [5, 5]
    assert recs[0]["starttime"] == base * 1_000_000
    assert recs[1]["starttime"] == (base + 60_000) * 1_000_000


# ---------------------------------------------------------------------------
# Spec loading
# ---------------------------------------------------------------------------

def test_legacy_max_samples_per_record_is_ignored_with_warning(tmp_path, capsys):
    spec_file = tmp_path / "spec.toml"
    spec_file.write_text(
        'root = "out"\n[encoding]\nmax_samples_per_record = 4096\n'
    )
    spec = mw.load_spec(spec_file)
    assert "max_samples_per_record" not in spec["encoding"]
    assert spec["encoding"]["max_record_length"] == 4096   # default still applies
    assert "obsolete" in capsys.readouterr().err


def test_bundled_spec_parses_and_is_version_3():
    """The shipped template is copied into the data dir on first run, so a
    typo in it breaks every fresh install."""
    from earthscope_positions import paths
    spec = mw.load_spec(paths.bundled_resources_dir() / "miniseed_path_spec.toml")
    assert spec["encoding"]["format_version"] == 3
    assert spec["encoding"]["max_record_length"] == 4096
    assert "max_samples_per_record" not in spec["encoding"]

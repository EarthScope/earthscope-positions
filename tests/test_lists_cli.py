"""`es-pos lists` — the restructured list CLI.

Covers the command surface (list / show-* / get-*), the --path option used to
open a list in an editor, and the geosncl normalisation the radial endpoint
needs.
"""
from __future__ import annotations

import json
import sys

import pytest

from earthscope_positions import paths
from earthscope_positions.stations import station_list as sl


def _run(*argv: str) -> None:
    old = sys.argv
    sys.argv = ["es-pos lists", *argv]
    try:
        sl.main()
    finally:
        sys.argv = old


@pytest.fixture
def populated(project_tree):
    """Two stream lists and one station list under the tmp data directory."""
    sl.save_stream_list("alpha", [
        {"geosncl": "P143.PB.LY_.10", "edid": "e1", "facility": "earthscope", "software": "pivot_rtx"},
        {"geosncl": "P157.NC.LY_.20", "edid": "e2", "facility": "usgs_menlo_park", "software": "rtnet"},
    ])
    sl.save_stream_list("beta", [
        {"geosncl": "P166.PW.LY_.00", "edid": "e3", "facility": "cwu", "software": "fastlane"},
    ])
    sl.save_station_list("sites", ["P143", "P157", "P166"])
    return project_tree


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------

def test_list_shows_both_kinds_with_counts(populated, capsys):
    _run("list")
    out = capsys.readouterr().out
    assert "Stream lists (2)" in out
    assert "Station lists (1)" in out
    assert "2 entries" in out    # alpha
    assert "1 entries" in out    # beta
    assert "3 entries" in out    # sites


def test_list_streams_only(populated, capsys):
    _run("list", "--streams")
    out = capsys.readouterr().out
    assert "Stream lists" in out
    assert "Station lists" not in out


def test_list_stations_only(populated, capsys):
    _run("list", "--stations")
    out = capsys.readouterr().out
    assert "Station lists" in out
    assert "Stream lists" not in out
    # The editing hint must name the kind actually shown.
    assert "show-stations" in out


def test_list_streams_and_stations_are_mutually_exclusive(populated):
    with pytest.raises(SystemExit):
        _run("list", "--streams", "--stations")


def test_list_handles_an_empty_data_directory(project_tree, capsys):
    _run("list")
    out = capsys.readouterr().out
    assert "Stream lists (0)" in out or "(none)" in out


# ---------------------------------------------------------------------------
# show-streams / show-stations
# ---------------------------------------------------------------------------

def test_show_streams_prints_contents(populated, capsys):
    _run("show-streams", "alpha")
    out = capsys.readouterr().out
    assert "P143.PB.LY_.10" in out
    assert "P157.NC.LY_.20" in out


def test_show_stations_prints_contents(populated, capsys):
    _run("show-stations", "sites")
    out = capsys.readouterr().out
    assert json.loads(out.splitlines()[0]) == {"station": "P143"}


@pytest.mark.parametrize("cmd,name,dirfn", [
    ("show-streams", "alpha", "stream_lists_dir"),
    ("show-stations", "sites", "station_lists_dir"),
])
def test_path_prints_only_an_absolute_path(populated, capsys, cmd, name, dirfn):
    """The output has to be usable as $EDITOR "$(es-pos lists ... --path)",
    so it must be exactly one absolute path and nothing else."""
    _run(cmd, name, "--path")
    out = capsys.readouterr().out
    lines = out.splitlines()
    assert len(lines) == 1
    expected = getattr(paths, dirfn)() / f"{name}.jsonl"
    assert lines[0] == str(expected.resolve())
    assert expected.exists()


def test_show_streams_and_show_stations_look_in_different_dirs(populated):
    """A station list is not visible to show-streams, and vice versa."""
    with pytest.raises(SystemExit):
        _run("show-streams", "sites")
    with pytest.raises(SystemExit):
        _run("show-stations", "alpha")


def test_show_missing_list_exits(populated):
    with pytest.raises(SystemExit):
        _run("show-streams", "does-not-exist")


# ---------------------------------------------------------------------------
# geosncl normalisation (radial endpoint namespaces its names)
# ---------------------------------------------------------------------------

def test_radial_geosncl_prefix_is_stripped():
    """/discover/gnss/radial returns "GEOSNCL:P156.NC.LY_.20"; the datasource
    endpoint returns it bare.  Unstripped, the prefix reaches saved lists and
    consumers silently read the station as "GEOSNCL:P156" -- parse_geosncl
    does not raise on it, the dot count is still 4."""
    rec = sl._record("e1", "GEOSNCL:P156.NC.LY_.20", "usgs_menlo_park", "rtnet")
    assert rec["geosncl"] == "P156.NC.LY_.20"


def test_bare_geosncl_is_left_alone():
    rec = sl._record("e1", "P156.NC.LY_.20", "usgs_menlo_park", "rtnet")
    assert rec["geosncl"] == "P156.NC.LY_.20"


def test_normalized_geosncl_parses_to_the_right_station():
    from earthscope_positions.export.miniseed_writer import parse_geosncl
    rec = sl._record("e1", "GEOSNCL:P156.NC.LY_.20", None, None)
    assert parse_geosncl(rec["geosncl"]).station == "P156"


def test_stations_derived_from_records(project_tree):
    records = [
        {"geosncl": "P143.PB.LY_.10"},
        {"geosncl": "P143.NC.LY_.20"},   # same station, different stream
        {"geosncl": "P157.PW.LY_.00"},
        {"geosncl": None},
    ]
    assert sl._stations_from_records(records) == ["P143", "P157"]


def test_list_shows_the_full_path_of_every_entry(populated, capsys):
    """Each row carries its own absolute path -- a row read out of scrollback
    has to be usable without the header still being visible."""
    _run("list")
    out = capsys.readouterr().out
    for name, dirfn in [("alpha", "stream_lists_dir"),
                        ("beta", "stream_lists_dir"),
                        ("sites", "station_lists_dir")]:
        expected = (getattr(paths, dirfn)() / f"{name}.jsonl").resolve()
        assert str(expected) in out


# ---------------------------------------------------------------------------
# --edit
# ---------------------------------------------------------------------------

@pytest.fixture
def fake_editor(tmp_path):
    """An 'editor' that appends a line, so an edit is observable."""
    script = tmp_path / "fake-editor.sh"
    script.write_text('#!/bin/sh\nprintf \'{"station":"P999"}\\n\' >> "$1"\n')
    script.chmod(0o755)
    return script


def test_edit_launches_the_editor_on_the_right_file(populated, fake_editor, monkeypatch, capsys):
    monkeypatch.setenv("EDITOR", str(fake_editor))
    monkeypatch.delenv("VISUAL", raising=False)
    _run("show-stations", "sites", "--edit")
    path = paths.station_lists_dir() / "sites.jsonl"
    assert '{"station":"P999"}' in path.read_text()


def test_edit_reports_the_entry_count_delta(populated, fake_editor, monkeypatch, capsys):
    monkeypatch.setenv("EDITOR", str(fake_editor))
    monkeypatch.delenv("VISUAL", raising=False)
    _run("show-stations", "sites", "--edit")
    err = capsys.readouterr().err
    assert "4 entries" in err          # was 3
    assert "+1" in err


def test_visual_takes_precedence_over_editor(populated, tmp_path, monkeypatch):
    marker = tmp_path / "visual-ran"
    visual = tmp_path / "visual.sh"
    visual.write_text(f'#!/bin/sh\ntouch {marker}\n')
    visual.chmod(0o755)
    monkeypatch.setenv("VISUAL", str(visual))
    monkeypatch.setenv("EDITOR", "/nonexistent-editor")
    _run("show-streams", "alpha", "--edit")
    assert marker.exists()


def test_editor_may_carry_arguments(populated, tmp_path, monkeypatch):
    """EDITOR="code -w" is common; it must be split, not exec'd as one name."""
    got = tmp_path / "args"
    ed = tmp_path / "ed.sh"
    ed.write_text(f'#!/bin/sh\necho "$@" > {got}\n')
    ed.chmod(0o755)
    monkeypatch.setenv("EDITOR", f"{ed} --wait")
    monkeypatch.delenv("VISUAL", raising=False)
    _run("show-streams", "alpha", "--edit")
    recorded = got.read_text().split()
    assert recorded[0] == "--wait"
    assert recorded[1] == str((paths.stream_lists_dir() / "alpha.jsonl").resolve())


def test_editor_failure_is_reported(populated, tmp_path, monkeypatch):
    failing = tmp_path / "fail.sh"
    failing.write_text("#!/bin/sh\nexit 3\n")
    failing.chmod(0o755)
    monkeypatch.setenv("EDITOR", str(failing))
    monkeypatch.delenv("VISUAL", raising=False)
    with pytest.raises(SystemExit):
        _run("show-streams", "alpha", "--edit")


def test_missing_editor_binary_is_reported(populated, monkeypatch):
    monkeypatch.setenv("EDITOR", "/definitely/not/an/editor")
    monkeypatch.delenv("VISUAL", raising=False)
    with pytest.raises(SystemExit):
        _run("show-streams", "alpha", "--edit")


def test_no_editor_configured_names_the_variable(populated, monkeypatch):
    monkeypatch.delenv("EDITOR", raising=False)
    monkeypatch.delenv("VISUAL", raising=False)
    monkeypatch.setattr("shutil.which", lambda *_a, **_k: None)
    with pytest.raises(SystemExit, match="EDITOR"):
        _run("show-streams", "alpha", "--edit")


def test_edit_and_path_are_mutually_exclusive(populated):
    with pytest.raises(SystemExit):
        _run("show-streams", "alpha", "--edit", "--path")

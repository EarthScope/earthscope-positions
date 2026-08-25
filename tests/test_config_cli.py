"""`es-pos config` — the commands that read and rewrite the persisted setting.

`move-data-dir` relocates real user data, so its refusal cases are covered
here rather than left to manual testing.
"""
from __future__ import annotations

import json
import pathlib

import pytest

from earthscope_positions import es_pos, paths


def _run(*argv: str) -> None:
    """Invoke the CLI as if from the command line."""
    import sys
    old = sys.argv
    sys.argv = ["es-pos", *argv]
    try:
        es_pos.main()
    finally:
        sys.argv = old


@pytest.fixture
def data_tree(tmp_path):
    """A populated data directory, recorded in an isolated config file."""
    paths.set_config_path(tmp_path / "cfg.json")
    src = tmp_path / "data"
    (src / "arrow" / "STA.NC.LY_.20").mkdir(parents=True)
    (src / "arrow" / "STA.NC.LY_.20" / "x.arrow").write_bytes(b"\x00" * 1024)
    (src / "stream-lists").mkdir()
    (src / "stream-lists" / "a.jsonl").write_text('{"geosncl":"STA.NC.LY_.20"}\n')
    paths.set_configured_data_dir(src)
    return src


# ---------------------------------------------------------------------------
# show / set-data-dir
# ---------------------------------------------------------------------------

def test_show_reports_the_deciding_layer(data_tree, capsys):
    _run("config", "show")
    out = capsys.readouterr().out
    assert str(data_tree) in out
    assert "config file" in out


def test_set_data_dir_writes_config_and_creates_dir(tmp_path, capsys):
    paths.set_config_path(tmp_path / "cfg.json")
    target = tmp_path / "brand-new"
    _run("config", "set-data-dir", str(target))
    assert target.is_dir()
    assert json.loads((tmp_path / "cfg.json").read_text())[
        paths.CONFIG_DATA_DIR_KEY] == str(target.resolve())


def test_set_data_dir_no_create(tmp_path):
    paths.set_config_path(tmp_path / "cfg.json")
    target = tmp_path / "not-made"
    _run("config", "set-data-dir", str(target), "--no-create")
    assert not target.exists()
    assert paths.configured_data_dir() == target.resolve()


# ---------------------------------------------------------------------------
# move-data-dir
# ---------------------------------------------------------------------------

def test_move_relocates_tree_and_updates_config(data_tree, tmp_path):
    dst = tmp_path / "moved"
    _run("config", "move-data-dir", str(dst), "--yes")
    assert not data_tree.exists()
    assert (dst / "arrow" / "STA.NC.LY_.20" / "x.arrow").read_bytes() == b"\x00" * 1024
    assert (dst / "stream-lists" / "a.jsonl").exists()
    assert paths.configured_data_dir() == dst.resolve()
    assert paths.base_dir() == dst.resolve()


def test_move_refuses_non_empty_destination(data_tree, tmp_path):
    dst = tmp_path / "occupied"
    dst.mkdir()
    (dst / "keep").write_text("mine")
    with pytest.raises(SystemExit):
        _run("config", "move-data-dir", str(dst), "--yes")
    assert data_tree.exists()                      # source untouched
    assert (dst / "keep").read_text() == "mine"    # destination untouched


def test_move_accepts_empty_existing_destination(data_tree, tmp_path):
    dst = tmp_path / "empty"
    dst.mkdir()
    _run("config", "move-data-dir", str(dst), "--yes")
    assert (dst / "arrow").is_dir()
    assert not data_tree.exists()


def test_move_refuses_own_subdirectory(data_tree):
    with pytest.raises(SystemExit):
        _run("config", "move-data-dir", str(data_tree / "inner"), "--yes")
    assert (data_tree / "arrow").is_dir()


def test_move_refuses_same_directory(data_tree):
    with pytest.raises(SystemExit):
        _run("config", "move-data-dir", str(data_tree), "--yes")
    assert (data_tree / "arrow").is_dir()


def test_move_refuses_missing_source(tmp_path):
    paths.set_config_path(tmp_path / "cfg.json")
    paths.set_configured_data_dir(tmp_path / "never-created")
    with pytest.raises(SystemExit):
        _run("config", "move-data-dir", str(tmp_path / "dst"), "--yes")


def test_move_leaves_config_alone_when_it_refuses(data_tree, tmp_path):
    before = paths.configured_data_dir()
    dst = tmp_path / "occupied"
    dst.mkdir()
    (dst / "f").write_text("x")
    with pytest.raises(SystemExit):
        _run("config", "move-data-dir", str(dst), "--yes")
    assert paths.configured_data_dir() == before


# ---------------------------------------------------------------------------
# Remembered directories: list / use / forget
# ---------------------------------------------------------------------------

def test_directories_are_remembered_in_first_seen_order(tmp_path):
    paths.set_config_path(tmp_path / "cfg.json")
    for name in ("one", "two", "three"):
        paths.set_configured_data_dir(tmp_path / name)
    assert [p.name for p in paths.known_data_dirs()] == ["one", "two", "three"]
    # Switching back must not reorder: the numbers in `list-data-dirs` have to
    # stay valid after a switch.
    paths.set_configured_data_dir(tmp_path / "one")
    assert [p.name for p in paths.known_data_dirs()] == ["one", "two", "three"]


def test_repeated_set_does_not_duplicate(tmp_path):
    paths.set_config_path(tmp_path / "cfg.json")
    for _ in range(3):
        paths.set_configured_data_dir(tmp_path / "same")
    assert len(paths.known_data_dirs()) == 1


def test_use_data_dir_by_number(tmp_path, capsys):
    paths.set_config_path(tmp_path / "cfg.json")
    for name in ("alpha", "beta", "gamma"):
        paths.set_configured_data_dir(tmp_path / name)
    _run("config", "use-data-dir", "1")
    assert paths.configured_data_dir() == (tmp_path / "alpha").resolve()
    assert paths.base_dir() == (tmp_path / "alpha").resolve()


def test_use_data_dir_by_path_remembers_new_entry(tmp_path):
    paths.set_config_path(tmp_path / "cfg.json")
    paths.set_configured_data_dir(tmp_path / "first")
    _run("config", "use-data-dir", str(tmp_path / "fresh"))
    assert paths.configured_data_dir() == (tmp_path / "fresh").resolve()
    assert (tmp_path / "fresh").resolve() in [p.resolve() for p in paths.known_data_dirs()]


def test_use_data_dir_rejects_out_of_range_number(tmp_path):
    paths.set_config_path(tmp_path / "cfg.json")
    paths.set_configured_data_dir(tmp_path / "only")
    with pytest.raises(SystemExit):
        _run("config", "use-data-dir", "7")


def test_list_data_dirs_marks_the_active_one(tmp_path, capsys):
    paths.set_config_path(tmp_path / "cfg.json")
    paths.set_configured_data_dir(tmp_path / "old")
    paths.set_configured_data_dir(tmp_path / "current")
    _run("config", "list-data-dirs")
    lines = [l for l in capsys.readouterr().out.splitlines() if "tmp" in l or "/" in l]
    active = [l for l in lines if l.strip().startswith("*")]
    assert len(active) == 1 and "current" in active[0]


def test_forget_removes_from_list_but_not_from_disk(tmp_path):
    paths.set_config_path(tmp_path / "cfg.json")
    stale = tmp_path / "stale"
    stale.mkdir()
    (stale / "keep.txt").write_text("data")
    paths.set_configured_data_dir(stale)
    paths.set_configured_data_dir(tmp_path / "active")
    _run("config", "forget-data-dir", str(stale))
    assert stale.resolve() not in [p.resolve() for p in paths.known_data_dirs()]
    assert (stale / "keep.txt").read_text() == "data"


def test_cannot_forget_the_active_directory(tmp_path):
    paths.set_config_path(tmp_path / "cfg.json")
    active = paths.set_configured_data_dir(tmp_path / "active")
    with pytest.raises(SystemExit):
        _run("config", "forget-data-dir", str(active))
    assert active.resolve() in [p.resolve() for p in paths.known_data_dirs()]


def test_move_drops_the_vacated_path_from_the_list(data_tree, tmp_path):
    """The old location no longer exists after a move, so offering it for
    switching would only ever fail."""
    dst = tmp_path / "moved"
    _run("config", "move-data-dir", str(dst), "--yes")
    remembered = [p.resolve() for p in paths.known_data_dirs()]
    assert dst.resolve() in remembered
    assert data_tree.resolve() not in remembered

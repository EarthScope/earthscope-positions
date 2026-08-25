"""Data-directory resolution.

Precedence: ES_POS_DATA_DIRECTORY > config file > first-run prompt >
built-in default.  There is no --data-directory flag.  The Arrow root is
always <base>/arrow.
"""
from __future__ import annotations

import json
import pathlib

import pytest

from earthscope_positions import paths


# ---------------------------------------------------------------------------
# Precedence
# ---------------------------------------------------------------------------

def test_config_file_sets_the_default(project_tree):
    # project_tree records <tmp>/data in the config file.
    assert paths.base_dir() == project_tree / "data"
    assert paths.base_dir_source() == "config"
    assert paths.arrow_dir() == project_tree / "data" / "arrow"
    assert paths.stream_lists_dir() == project_tree / "data" / "stream-lists"
    assert paths.plots_dir() == project_tree / "data" / "plots"


def test_env_var_overrides_config(project_tree, monkeypatch):
    monkeypatch.setenv(paths.ENV_VAR, "/env/data")
    assert paths.base_dir() == pathlib.Path("/env/data")
    assert paths.base_dir_source() == "env"
    assert paths.arrow_dir() == pathlib.Path("/env/data/arrow")


def test_no_data_directory_flag_exists(project_tree):
    """The flag was removed: a third way to say the same thing, on every
    data-touching subcommand, caused more confusion than it solved."""
    assert not hasattr(paths, "set_base_dir")
    from earthscope_positions import es_pos
    assert not hasattr(es_pos, "_add_data_dir_args")
    help_text = es_pos._build_top_parser()[0].format_help()
    assert "--data-directory" not in help_text


def test_falls_back_to_home_default_when_unconfigured(tmp_path, monkeypatch, capsys):
    """With nothing set anywhere, the default is ~/earthscope-positions --
    never the CWD, which is what the old project-root walk used to give."""
    monkeypatch.delenv(paths.ENV_VAR, raising=False)
    paths.set_config_path(tmp_path / "absent.json")   # no config file
    paths.reset_cache()
    paths.set_interactive(False)
    assert paths.base_dir() == pathlib.Path.home() / "earthscope-positions"
    assert paths.base_dir_source() == "default"
    assert "No data directory configured" in capsys.readouterr().err


def test_cwd_is_never_consulted(tmp_path, monkeypatch):
    """The old behaviour wrote into any ancestor directory holding a
    pyproject.toml.  Standing in one must now change nothing."""
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'unrelated'\n")
    (tmp_path / "data").mkdir()
    monkeypatch.chdir(tmp_path)
    paths.set_config_path(tmp_path / "cfg.json")
    paths.set_configured_data_dir(tmp_path / "elsewhere")
    assert paths.base_dir() == (tmp_path / "elsewhere").resolve()


def test_expanduser(project_tree, monkeypatch):
    monkeypatch.setenv(paths.ENV_VAR, "~/es-data")
    paths.reset_cache()
    assert paths.base_dir() == pathlib.Path("~/es-data").expanduser()


def test_arrow_always_under_base(project_tree, monkeypatch):
    monkeypatch.setenv(paths.ENV_VAR, "/flag/data")
    paths.reset_cache()
    assert paths.arrow_dir() == pathlib.Path("/flag/data/arrow")
    assert paths.stream_lists_dir() == pathlib.Path("/flag/data/stream-lists")
    assert paths.plots_dir() == pathlib.Path("/flag/data/plots")
    assert not hasattr(paths, "set_arrow_dir")


# ---------------------------------------------------------------------------
# Config file
# ---------------------------------------------------------------------------

def test_set_configured_data_dir_round_trips(tmp_path):
    paths.set_config_path(tmp_path / "cfg.json")
    saved = paths.set_configured_data_dir(tmp_path / "somewhere")
    assert saved == (tmp_path / "somewhere").resolve()
    assert paths.configured_data_dir() == saved
    on_disk = json.loads((tmp_path / "cfg.json").read_text())
    assert on_disk[paths.CONFIG_DATA_DIR_KEY] == str(saved)


def test_set_configured_data_dir_preserves_other_keys(tmp_path):
    cfg = tmp_path / "cfg.json"
    paths.set_config_path(cfg)
    cfg.write_text(json.dumps({"unrelated": "keep me"}))
    paths.set_configured_data_dir(tmp_path / "d")
    on_disk = json.loads(cfg.read_text())
    assert on_disk["unrelated"] == "keep me"
    assert paths.CONFIG_DATA_DIR_KEY in on_disk


def test_corrupt_config_degrades_to_unconfigured(tmp_path, capsys):
    """A broken config must not make the tool unusable."""
    cfg = tmp_path / "cfg.json"
    paths.set_config_path(cfg)
    cfg.write_text("{not json at all")
    assert paths.configured_data_dir() is None
    assert "Ignoring unreadable config" in capsys.readouterr().err


def test_config_env_var_relocates_the_file(tmp_path, monkeypatch):
    paths.set_config_path(None)     # fall through to the env var
    monkeypatch.setenv(paths.CONFIG_ENV_VAR, str(tmp_path / "custom.json"))
    assert paths.config_path() == tmp_path / "custom.json"


# ---------------------------------------------------------------------------
# Override-vs-config mismatch notice
# ---------------------------------------------------------------------------

def test_env_disagreeing_with_config_is_reported(tmp_path, monkeypatch, capsys):
    paths.set_config_path(tmp_path / "cfg.json")
    paths.set_configured_data_dir(tmp_path / "configured")
    monkeypatch.setenv(paths.ENV_VAR, str(tmp_path / "override"))
    paths.reset_cache()
    assert paths.base_dir() == tmp_path / "override"
    err = capsys.readouterr().err
    assert paths.ENV_VAR in err
    assert str(tmp_path / "configured") in err
    assert "es-pos config set-data-dir" in err


def test_matching_override_is_silent(tmp_path, monkeypatch, capsys):
    """No notice when the override agrees with the config -- this is the
    webserver's own subprocesses, which are handed the resolved path."""
    paths.set_config_path(tmp_path / "cfg.json")
    configured = paths.set_configured_data_dir(tmp_path / "same")
    monkeypatch.setenv(paths.ENV_VAR, str(configured))
    paths.reset_cache()
    assert paths.base_dir() == configured
    assert capsys.readouterr().err == ""


def test_mismatch_reported_once_per_process_tree(tmp_path, monkeypatch, capsys):
    """The notice sets an env marker so spawned children stay quiet instead of
    repeating it into the web UI log on every export."""
    paths.set_config_path(tmp_path / "cfg.json")
    paths.set_configured_data_dir(tmp_path / "configured")
    monkeypatch.setenv(paths.ENV_VAR, str(tmp_path / "override"))
    paths.reset_cache()
    paths.base_dir()
    assert capsys.readouterr().err != ""

    paths.reset_cache()
    paths.base_dir()
    assert capsys.readouterr().err == ""


# ---------------------------------------------------------------------------
# Prompting
# ---------------------------------------------------------------------------

def test_no_prompt_when_not_interactive(tmp_path, monkeypatch, capsys):
    paths.set_config_path(tmp_path / "absent.json")
    paths.reset_cache()
    paths.set_interactive(False)
    monkeypatch.setattr("builtins.input", lambda *a: pytest.fail("must not prompt"))
    assert paths.base_dir() == paths.default_data_dir()


def test_prompt_saves_the_answer(tmp_path, monkeypatch, capsys):
    paths.set_config_path(tmp_path / "cfg.json")
    paths.reset_cache()
    paths.set_interactive(True)
    monkeypatch.setattr("sys.stdin", type("_S", (), {"isatty": staticmethod(lambda: True)})())
    monkeypatch.setattr("builtins.input", lambda *a: str(tmp_path / "chosen"))
    assert paths.base_dir() == (tmp_path / "chosen").resolve()
    assert paths.base_dir_source() == "prompt"
    assert paths.configured_data_dir() == (tmp_path / "chosen").resolve()


def test_empty_prompt_answer_takes_the_default(tmp_path, monkeypatch):
    paths.set_config_path(tmp_path / "cfg.json")
    paths.reset_cache()
    paths.set_interactive(True)
    monkeypatch.setattr("sys.stdin", type("_S", (), {"isatty": staticmethod(lambda: True)})())
    monkeypatch.setattr("builtins.input", lambda *a: "  ")
    assert paths.base_dir() == paths.default_data_dir().resolve()

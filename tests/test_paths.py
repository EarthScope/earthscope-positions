"""Data-directory resolution precedence: --data-directory > env var > ./data,
with --arrow-data-directory overriding just the Arrow root."""
from __future__ import annotations

import pathlib

from earthscope_positions import paths


def test_default_is_project_data(project_tree):
    # project_tree chdirs into a tmp project root containing pyproject.toml
    assert paths.base_dir() == project_tree / "data"
    assert paths.arrow_dir() == project_tree / "data" / "arrow"
    assert paths.station_lists_dir() == project_tree / "data" / "station-lists"
    assert paths.plots_dir() == project_tree / "data" / "plots"


def test_env_var_overrides_default(project_tree, monkeypatch):
    monkeypatch.setenv(paths.ENV_VAR, "/env/data")
    assert paths.base_dir() == pathlib.Path("/env/data")
    assert paths.arrow_dir() == pathlib.Path("/env/data/arrow")


def test_flag_supersedes_env(project_tree, monkeypatch):
    monkeypatch.setenv(paths.ENV_VAR, "/env/data")
    paths.set_base_dir("/flag/data")
    assert paths.base_dir() == pathlib.Path("/flag/data")
    assert paths.station_lists_dir() == pathlib.Path("/flag/data/station-lists")


def test_arrow_override_supersedes_base(project_tree):
    paths.set_base_dir("/flag/data")
    paths.set_arrow_dir("/fast/arrow")
    # Arrow points at the override; other subdirs still derive from the base.
    assert paths.arrow_dir() == pathlib.Path("/fast/arrow")
    assert paths.station_lists_dir() == pathlib.Path("/flag/data/station-lists")
    assert paths.plots_dir() == pathlib.Path("/flag/data/plots")


def test_expanduser(project_tree):
    paths.set_base_dir("~/es-data")
    assert paths.base_dir() == pathlib.Path("~/es-data").expanduser()

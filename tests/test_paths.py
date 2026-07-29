"""Data-directory resolution precedence: --data-directory > env var > ./data.
The Arrow root is always <base>/arrow."""
from __future__ import annotations

import pathlib

from earthscope_positions import paths


def test_default_is_project_data(project_tree):
    # project_tree chdirs into a tmp project root containing pyproject.toml
    assert paths.base_dir() == project_tree / "data"
    assert paths.arrow_dir() == project_tree / "data" / "arrow"
    assert paths.stream_lists_dir() == project_tree / "data" / "stream-lists"
    assert paths.plots_dir() == project_tree / "data" / "plots"


def test_env_var_overrides_default(project_tree, monkeypatch):
    monkeypatch.setenv(paths.ENV_VAR, "/env/data")
    assert paths.base_dir() == pathlib.Path("/env/data")
    assert paths.arrow_dir() == pathlib.Path("/env/data/arrow")


def test_flag_supersedes_env(project_tree, monkeypatch):
    monkeypatch.setenv(paths.ENV_VAR, "/env/data")
    paths.set_base_dir("/flag/data")
    assert paths.base_dir() == pathlib.Path("/flag/data")
    assert paths.stream_lists_dir() == pathlib.Path("/flag/data/stream-lists")


def test_arrow_always_under_base(project_tree):
    paths.set_base_dir("/flag/data")
    # Arrow is always <base>/arrow; there is no independent override.
    assert paths.arrow_dir() == pathlib.Path("/flag/data/arrow")
    assert paths.stream_lists_dir() == pathlib.Path("/flag/data/stream-lists")
    assert paths.plots_dir() == pathlib.Path("/flag/data/plots")
    assert not hasattr(paths, "set_arrow_dir")


def test_expanduser(project_tree):
    paths.set_base_dir("~/es-data")
    assert paths.base_dir() == pathlib.Path("~/es-data").expanduser()

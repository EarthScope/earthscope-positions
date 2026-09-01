"""The webserver's view of the environment.

The UI badge is the only thing standing between a stage tab and being mistaken
for a production one, so the server decides whether to show it (rather than the
client inferring it) and these pin that decision.
"""
from __future__ import annotations

import pytest

from earthscope_positions import environment, paths


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch):
    monkeypatch.delenv(environment.ENV_VAR, raising=False)
    monkeypatch.delenv(environment.PROFILE_ENV_VAR, raising=False)
    environment.reset_cache()
    yield
    environment.reset_cache()


@pytest.fixture
def client(project_tree):
    from fastapi.testclient import TestClient
    import earthscope_positions.webserver.webserver as w
    return TestClient(w.app)


def test_config_reports_production_without_a_badge(client):
    cfg = client.get("/api/config").json()
    assert cfg["environment"] == "prod"
    assert cfg["environment_badge"] is False
    assert cfg["api_url"] == "https://api.earthscope.org"


def test_config_badges_stage(client):
    environment.write_marker(paths.base_dir(), "stage")
    cfg = client.get("/api/config").json()
    assert cfg["environment"] == "stage"
    assert cfg["environment_label"] == "Stage"
    assert cfg["environment_badge"] is True
    assert cfg["api_url"] == "https://api.dev.earthscope.org"
    assert cfg["es_profile"] == "stage"


def test_data_directory_endpoint_reports_the_environment(client):
    environment.write_marker(paths.base_dir(), "stage", profile="dev")
    cfg = client.get("/api/config/data-directory").json()
    assert cfg["environment"] == "stage"
    assert cfg["environment_source"] == "data-dir"
    assert cfg["es_profile"] == "dev"
    assert cfg["environment_marker_file"].endswith(".config/environment.json")


def test_known_directories_carry_their_own_environment(client, tmp_path):
    other = tmp_path / "stage-tree"
    other.mkdir()
    environment.write_marker(other, "stage")
    paths.set_configured_data_dir(other, remember=True)
    paths.set_configured_data_dir(paths.base_dir())

    entries = client.get("/api/config/data-directory").json()["known_data_directories"]
    by_path = {e["path"]: e for e in entries}
    assert by_path[str(other.resolve())]["environment"] == "stage"


def test_file_explorer_hides_the_config_directory(client):
    """Hand-editing the marker would route around the switch guard, so .config
    is not offered in the browser."""
    environment.write_marker(paths.base_dir(), "stage")
    names = [e["name"] for e in client.get("/api/files/list").json()["entries"]]
    assert ".config" not in names


def test_child_env_carries_the_environment_to_subprocesses():
    """A child that re-resolved differently would fetch the wrong EDIDs into
    the tree its parent is serving."""
    import earthscope_positions.webserver.webserver as w

    environment.write_marker(paths.base_dir(), "stage", profile="dev")
    env = w._child_env()
    assert env[environment.ENV_VAR] == "stage"
    assert env[environment.PROFILE_ENV_VAR] == "dev"
    assert env[paths.ENV_VAR] == str(paths.base_dir())

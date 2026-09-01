"""Environment (production vs stage) resolution and the switch guard.

The invariant under test throughout: prod and stage issue different EDIDs for
the same station, so a data directory is only ever one of them, and the only
thing that can put a directory on stage is `es-pos config use-data-dir --stage`.
"""
from __future__ import annotations

import json

import pytest

from earthscope_positions import environment, es_pos, paths


def _run(*argv: str) -> None:
    import sys
    old = sys.argv
    sys.argv = ["es-pos", *argv]
    try:
        es_pos.main()
    finally:
        sys.argv = old


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch):
    """No inherited override, and no cached answer from a previous test."""
    monkeypatch.delenv(environment.ENV_VAR, raising=False)
    monkeypatch.delenv(environment.PROFILE_ENV_VAR, raising=False)
    environment.reset_cache()
    yield
    environment.reset_cache()


@pytest.fixture
def data_dir(tmp_path):
    d = tmp_path / "data"
    d.mkdir()
    paths.set_configured_data_dir(d)
    return d


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------

def test_unmarked_directory_is_production(data_dir):
    assert environment.name() == "prod"
    assert environment.current_source() == "default"
    assert environment.api_url() == "https://api.earthscope.org"
    assert environment.profile() == "default"


def test_marked_directory_resolves_to_stage(data_dir):
    environment.write_marker(data_dir, "stage")
    assert environment.name() == "stage"
    assert environment.current_source() == "data-dir"
    assert environment.api_url() == "https://api.dev.earthscope.org"
    assert environment.profile() == "stage"


def test_marker_lives_under_dot_config(data_dir):
    marker = environment.write_marker(data_dir, "stage")
    assert marker == data_dir / ".config" / "environment.json"
    assert json.loads(marker.read_text())["environment"] == "stage"


def test_environment_follows_the_active_data_directory(tmp_path):
    prod = tmp_path / "prod"
    stage = tmp_path / "stage"
    prod.mkdir()
    stage.mkdir()
    environment.write_marker(stage, "stage")

    paths.set_configured_data_dir(prod)
    assert environment.name() == "prod"
    paths.set_configured_data_dir(stage)
    assert environment.name() == "stage"


def test_env_var_overrides_the_marker(data_dir, monkeypatch):
    """The variable exists so the webserver can pin its children, not as a
    user-facing switch -- but when it is set it has to win, or a child could
    resolve differently from the parent that spawned it."""
    environment.write_marker(data_dir, "stage")
    monkeypatch.setenv(environment.ENV_VAR, "prod")
    assert environment.name() == "prod"
    assert environment.current_source() == "env"


def test_es_profile_overrides_the_environment_default(data_dir, monkeypatch):
    environment.write_marker(data_dir, "stage")
    monkeypatch.setenv(environment.PROFILE_ENV_VAR, "my-dev")
    assert environment.profile() == "my-dev"
    assert environment.api_url() == "https://api.dev.earthscope.org"


def test_marker_can_pin_its_own_profile(data_dir):
    environment.write_marker(data_dir, "stage", profile="dev")
    assert environment.profile() == "dev"
    assert environment.name() == "stage"


def test_unreadable_marker_degrades_to_production(data_dir, capsys):
    (data_dir / ".config").mkdir()
    (data_dir / ".config" / "environment.json").write_text("{not json")
    assert environment.name() == "prod"
    assert "unreadable environment marker" in capsys.readouterr().err


def test_unknown_environment_name_is_an_error_not_a_default(data_dir):
    (data_dir / ".config").mkdir()
    (data_dir / ".config" / "environment.json").write_text(
        json.dumps({"environment": "from-the-future"})
    )
    with pytest.raises(ValueError, match="from-the-future"):
        environment.name()


def test_child_env_pins_both_environment_and_profile(data_dir):
    environment.write_marker(data_dir, "stage", profile="dev")
    assert environment.child_env() == {
        environment.ENV_VAR: "stage",
        environment.PROFILE_ENV_VAR: "dev",
    }


# ---------------------------------------------------------------------------
# Switch guard
# ---------------------------------------------------------------------------

def test_empty_directory_may_be_switched(data_dir):
    assert environment.describe_switch_conflict(data_dir, "stage") is None


def test_populated_directory_may_not_be_switched(data_dir):
    (data_dir / "arrow" / "P143.PB.LY_.20").mkdir(parents=True)
    (data_dir / "arrow" / "P143.PB.LY_.20" / "x.arrow").write_bytes(b"")
    conflict = environment.describe_switch_conflict(data_dir, "stage")
    assert conflict is not None
    assert "different EDIDs" in conflict


def test_switching_to_the_environment_it_already_has_is_not_a_conflict(data_dir):
    (data_dir / "arrow").mkdir()
    (data_dir / "arrow" / "x").mkdir()
    environment.write_marker(data_dir, "stage")
    assert environment.describe_switch_conflict(data_dir, "stage") is None


def test_plots_alone_do_not_block_a_switch(data_dir):
    """Only EDID-bearing trees make a directory unsafe to re-point; generated
    plots and seeded resources carry no identifiers."""
    (data_dir / "plots").mkdir()
    (data_dir / "plots" / "a.png").write_bytes(b"")
    (data_dir / "resources").mkdir()
    (data_dir / "resources" / "coordinates.csv").write_text("x\n")
    assert environment.describe_switch_conflict(data_dir, "stage") is None


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def test_use_data_dir_stage_marks_and_activates(tmp_path, capsys):
    target = tmp_path / "stagedir"
    _run("config", "use-data-dir", "--stage", str(target))
    out = capsys.readouterr().out
    assert (target / ".config" / "environment.json").exists()
    assert paths.configured_data_dir() == target.resolve()
    assert "Stage (stage)" in out
    assert "api.dev.earthscope.org" in out


def test_use_data_dir_without_stage_leaves_the_environment_alone(tmp_path, capsys):
    """The whole point of the flag: switching to a directory must not silently
    change which deployment it is tied to."""
    target = tmp_path / "stagedir"
    _run("config", "use-data-dir", "--stage", str(target))
    other = tmp_path / "proddir"
    _run("config", "use-data-dir", str(other))
    capsys.readouterr()

    _run("config", "use-data-dir", str(target))
    assert "Stage (stage)" in capsys.readouterr().out


def test_use_data_dir_prod_switches_back(tmp_path, capsys):
    target = tmp_path / "d"
    _run("config", "use-data-dir", "--stage", str(target))
    capsys.readouterr()
    _run("config", "use-data-dir", "--prod", str(target))
    out = capsys.readouterr().out
    assert "Production (prod)" in out
    assert json.loads(
        (target / ".config" / "environment.json").read_text()
    )["environment"] == "prod"


def test_use_data_dir_stage_refuses_a_populated_prod_directory(tmp_path, capsys):
    target = tmp_path / "d"
    (target / "arrow" / "P143.PB.LY_.20").mkdir(parents=True)
    (target / "arrow" / "P143.PB.LY_.20" / "x.arrow").write_bytes(b"")
    with pytest.raises(SystemExit):
        _run("config", "use-data-dir", "--stage", str(target))
    assert not (target / ".config").exists()


def test_refusal_does_not_switch_the_active_directory(tmp_path, data_dir):
    """A refused switch has to be a no-op on both halves -- marking and
    activating -- or the user is left on a directory the command declined to
    configure."""
    target = tmp_path / "d"
    (target / "arrow" / "S").mkdir(parents=True)
    (target / "arrow" / "S" / "x.arrow").write_bytes(b"")
    with pytest.raises(SystemExit):
        _run("config", "use-data-dir", "--stage", str(target))
    assert paths.configured_data_dir() == data_dir.resolve()


def test_force_overrides_the_refusal(tmp_path, capsys):
    target = tmp_path / "d"
    (target / "arrow" / "S").mkdir(parents=True)
    (target / "arrow" / "S" / "x.arrow").write_bytes(b"")
    _run("config", "use-data-dir", "--stage", "--force", str(target))
    out = capsys.readouterr().out
    assert "Stage (stage)" in out
    assert "mixes environments" in out


def test_use_data_dir_records_a_custom_profile(tmp_path, capsys):
    target = tmp_path / "d"
    _run("config", "use-data-dir", "--stage", "--profile", "dev", str(target))
    assert "es profile:    dev" in capsys.readouterr().out
    assert json.loads(
        (target / ".config" / "environment.json").read_text()
    )["profile"] == "dev"


def test_profile_without_an_environment_flag_is_rejected(tmp_path):
    with pytest.raises(SystemExit):
        _run("config", "use-data-dir", "--profile", "dev", str(tmp_path / "d"))


def test_stage_and_prod_are_mutually_exclusive(tmp_path):
    with pytest.raises(SystemExit):
        _run("config", "use-data-dir", "--stage", "--prod", str(tmp_path / "d"))


def test_set_data_dir_cannot_enable_stage(tmp_path, capsys):
    """`use-data-dir --stage` is the single route onto stage; set-data-dir has
    no flag for it and must leave a directory on production."""
    target = tmp_path / "d"
    _run("config", "set-data-dir", str(target))
    out = capsys.readouterr().out
    assert "Production (prod)" in out
    assert not (target / ".config").exists()


def test_config_show_reports_the_environment(tmp_path, capsys):
    target = tmp_path / "d"
    _run("config", "use-data-dir", "--stage", str(target))
    capsys.readouterr()
    _run("config", "show")
    out = capsys.readouterr().out
    assert "Environment:     Stage (stage)" in out
    assert "https://api.dev.earthscope.org" in out


def test_list_data_dirs_tags_stage_directories(tmp_path, capsys):
    stage = tmp_path / "s"
    prod = tmp_path / "p"
    _run("config", "use-data-dir", "--stage", str(stage))
    _run("config", "use-data-dir", str(prod))
    capsys.readouterr()
    _run("config", "list-data-dirs")
    lines = capsys.readouterr().out.splitlines()
    stage_line = next(ln for ln in lines if str(stage) in ln)
    prod_line = next(ln for ln in lines if str(prod) in ln)
    assert "[Stage]" in stage_line
    assert "[" not in prod_line.split(str(prod))[1]


def test_move_data_dir_carries_the_environment_along(tmp_path, capsys):
    src = tmp_path / "src"
    _run("config", "use-data-dir", "--stage", str(src))
    (src / "arrow").mkdir()
    dst = tmp_path / "dst"
    capsys.readouterr()
    _run("config", "move-data-dir", "--yes", str(dst))
    out = capsys.readouterr().out
    assert (dst / ".config" / "environment.json").exists()
    assert "Stage (stage)" in out

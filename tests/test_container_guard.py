"""Container guard: refuse to run against a data directory that is not on a mount.

The guard checks the invariant that actually matters — will data written here
survive the container — rather than trying to prove which launcher started us.
An env var the launcher sets can be exported by hand, so it is advisory only.
"""
from __future__ import annotations

import pathlib

import pytest

from earthscope_positions import paths

# The container's own overlay root only — nothing bind-mounted.
EPHEMERAL = "25 30 0:23 / / rw,relatime - overlay overlay rw\n"

# A host directory bind-mounted at /data.
MOUNTED = EPHEMERAL + "99 25 8:1 /host /data rw,relatime - ext4 /dev/sda1 rw\n"


@pytest.fixture
def in_container(monkeypatch):
    monkeypatch.setattr(paths, "in_container", lambda: True)
    monkeypatch.delenv(paths.ALLOW_EPHEMERAL_ENV_VAR, raising=False)
    monkeypatch.delenv(paths.HOST_DATA_DIR_ENV_VAR, raising=False)


# ---------------------------------------------------------------------------
# Mount detection
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("directory,expected", [
    ("/data", True),
    ("/data/arrow", True),          # an ancestor being mounted is enough
    ("/data/arrow/STA/202601", True),
    ("/app/data", False),           # the stale-image path — not a mount
    ("/root/whatever", False),
])
def test_mount_detection(directory, expected):
    assert paths.data_dir_is_persistent(pathlib.Path(directory), MOUNTED) is expected


def test_container_root_alone_is_not_persistence():
    """`/` is always a mount inside a container; counting it would make the
    check pass for every path and defeat the point."""
    assert paths.data_dir_is_persistent(pathlib.Path("/data"), EPHEMERAL) is False
    assert paths.data_dir_is_persistent(pathlib.Path("/"), EPHEMERAL) is False


def test_unknown_when_mountinfo_is_unavailable(monkeypatch):
    """No /proc (macOS, BSD) must read as 'cannot tell', not 'not persistent'."""
    monkeypatch.setattr(pathlib.Path, "read_text",
                        lambda self, **kw: (_ for _ in ()).throw(OSError()))
    assert paths.data_dir_is_persistent(pathlib.Path("/data"), None) is None


def test_mountinfo_paths_with_spaces():
    mi = EPHEMERAL + "99 25 8:1 /host /my\\040data rw - ext4 /dev/sda1 rw\n"
    assert paths.data_dir_is_persistent(pathlib.Path("/my data"), mi) is True


# ---------------------------------------------------------------------------
# The guard
# ---------------------------------------------------------------------------

def test_no_problems_outside_a_container(monkeypatch):
    monkeypatch.setattr(paths, "in_container", lambda: False)
    assert paths.container_data_dir_problems(pathlib.Path("/data"), EPHEMERAL) == []


def test_ephemeral_data_dir_is_a_problem(in_container):
    problems = paths.container_data_dir_problems(pathlib.Path("/data"), EPHEMERAL)
    assert problems
    joined = "\n".join(problems)
    assert "lost when the container stops" in joined
    assert "es-pos-docker.sh run" in joined          # tells you the fix
    assert paths.ALLOW_EPHEMERAL_ENV_VAR in joined   # and the escape hatch


def test_mounted_data_dir_is_fine(in_container):
    assert paths.container_data_dir_problems(pathlib.Path("/data"), MOUNTED) == []


def test_unknown_persistence_does_not_block(in_container):
    """Never block on a check that could not be performed."""
    assert paths.container_data_dir_problems(pathlib.Path("/data"), None) == [] or \
        paths.data_dir_is_persistent(pathlib.Path("/data"), None) is not None


def test_escape_hatch_allows_ephemeral(in_container, monkeypatch):
    monkeypatch.setenv(paths.ALLOW_EPHEMERAL_ENV_VAR, "1")
    assert paths.container_data_dir_problems(pathlib.Path("/data"), EPHEMERAL) == []


@pytest.mark.parametrize("value", ["", "0", "false"])
def test_escape_hatch_falsy_values_still_guard(in_container, monkeypatch, value):
    monkeypatch.setenv(paths.ALLOW_EPHEMERAL_ENV_VAR, value)
    assert paths.container_data_dir_problems(pathlib.Path("/data"), EPHEMERAL)


# ---------------------------------------------------------------------------
# Launcher detection is advisory only
# ---------------------------------------------------------------------------

def test_missing_launcher_var_is_a_note_not_a_failure(in_container):
    """docker-compose and Kubernetes mount correctly without the script, so a
    missing launcher variable must never be fatal."""
    assert paths.container_data_dir_problems(pathlib.Path("/data"), MOUNTED) == []
    notes = paths.container_data_dir_notes(pathlib.Path("/data"))
    assert notes and "not through es-pos-docker.sh" in notes[0]


def test_no_note_when_the_launcher_reported_the_host_path(in_container, monkeypatch):
    monkeypatch.setenv(paths.HOST_DATA_DIR_ENV_VAR, "/Users/someone/earthscope-positions")
    assert paths.container_data_dir_notes(pathlib.Path("/data")) == []


def test_notes_are_empty_outside_a_container(monkeypatch):
    monkeypatch.setattr(paths, "in_container", lambda: False)
    assert paths.container_data_dir_notes(pathlib.Path("/data")) == []

"""Central resolver for the earthscope-positions data-directory layout.

The **base data directory** is resolved with this precedence:

    1. an explicit path set via :func:`set_base_dir`  (CLI ``--data-directory``)
    2. the ``ES_POS_DATA_DIRECTORY`` environment variable
    3. ``<project-root>/data``   (the default, i.e. ``./data``)

Every data sub-directory (``arrow/``, ``station-lists/``, ``plots/``,
``positions_diagnose/``) derives from the base.  The Arrow sub-directory can be
overridden independently via :func:`set_arrow_dir` (CLI
``--arrow-data-directory``), which supersedes the base for Arrow data only.

Import this module and call the accessor functions (``arrow_dir()``,
``station_lists_dir()``, …) rather than constructing ``.../data/...`` paths by
hand, so a single flag/env var controls the whole tree.
"""
from __future__ import annotations

import os
import pathlib

ENV_VAR = "ES_POS_DATA_DIRECTORY"

_base_override: pathlib.Path | None = None
_arrow_override: pathlib.Path | None = None


def project_root() -> pathlib.Path:
    """Nearest ancestor of the CWD containing pyproject.toml, else the CWD."""
    for p in [pathlib.Path.cwd(), *pathlib.Path.cwd().parents]:
        if (p / "pyproject.toml").exists():
            return p
    return pathlib.Path.cwd()


def set_base_dir(path: "str | os.PathLike[str] | None") -> None:
    """Set (or clear, with ``None``) the base data-directory override.

    Wired to the CLI ``--data-directory`` flag.  A falsy value leaves resolution
    to the environment variable / default.
    """
    global _base_override
    _base_override = pathlib.Path(path).expanduser() if path else None


def set_arrow_dir(path: "str | os.PathLike[str] | None") -> None:
    """Set (or clear, with ``None``) the Arrow-root override.

    Wired to the CLI ``--arrow-data-directory`` flag.  When set, it supersedes
    the base for Arrow data only (``station-lists/``, ``plots/`` still derive
    from the base).
    """
    global _arrow_override
    _arrow_override = pathlib.Path(path).expanduser() if path else None


def base_dir() -> pathlib.Path:
    """Return the resolved base data directory (see module docstring)."""
    if _base_override is not None:
        return _base_override
    env = os.environ.get(ENV_VAR)
    if env:
        return pathlib.Path(env).expanduser()
    return project_root() / "data"


def arrow_dir() -> pathlib.Path:
    """Root of the Arrow position-data tree (``<base>/arrow`` unless overridden)."""
    if _arrow_override is not None:
        return _arrow_override
    return base_dir() / "arrow"


def station_lists_dir() -> pathlib.Path:
    """Directory holding station-list JSONL files (``<base>/station-lists``)."""
    return base_dir() / "station-lists"


def plots_dir() -> pathlib.Path:
    """Directory holding generated plot images (``<base>/plots``)."""
    return base_dir() / "plots"


def positions_diagnose_dir() -> pathlib.Path:
    """Directory holding positions-diagnose output (``<base>/positions_diagnose``)."""
    return base_dir() / "positions_diagnose"

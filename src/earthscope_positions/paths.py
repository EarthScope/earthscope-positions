"""Central resolver for the earthscope-positions data-directory layout.

The **base data directory** is resolved with this precedence:

    1. an explicit path set via :func:`set_base_dir`  (CLI ``--data-directory``)
    2. the ``ES_POS_DATA_DIRECTORY`` environment variable
    3. ``<project-root>/data``   (the default, i.e. ``./data``)

Every data sub-directory (``arrow/``, ``stream-lists/``, ``station-lists/``,
``plots/``, ``positions_diagnose/``) derives from the base — including the Arrow
data root, which is always ``<base>/arrow``.

Import this module and call the accessor functions (``arrow_dir()``,
``stream_lists_dir()``, …) rather than constructing ``.../data/...`` paths by
hand, so a single flag/env var controls the whole tree.
"""
from __future__ import annotations

import os
import pathlib

ENV_VAR = "ES_POS_DATA_DIRECTORY"

_base_override: pathlib.Path | None = None


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


def base_dir() -> pathlib.Path:
    """Return the resolved base data directory (see module docstring)."""
    if _base_override is not None:
        return _base_override
    env = os.environ.get(ENV_VAR)
    if env:
        return pathlib.Path(env).expanduser()
    return project_root() / "data"


def arrow_dir() -> pathlib.Path:
    """Root of the Arrow position-data tree — always ``<base>/arrow``."""
    return base_dir() / "arrow"


def stream_lists_dir() -> pathlib.Path:
    """Directory holding **stream**-list JSONL files (``<base>/stream-lists``).

    These hold full geosncl (stream) records and are consumed by
    replay/fetch/PPSD/export.  Station (station-code) lists live in
    :func:`station_lists_dir`.
    """
    return base_dir() / "stream-lists"


def station_lists_dir() -> pathlib.Path:
    """Directory holding **station**-list JSONL files (``<base>/station-lists``).

    These hold station codes (one ``{"station": "P143"}`` per line) — the
    down-selected-stations lists produced by the Station List Builder and used as
    include/exclude sets by the Stream List Builder.
    """
    return base_dir() / "station-lists"


def plots_dir() -> pathlib.Path:
    """Directory holding generated plot images (``<base>/plots``)."""
    return base_dir() / "plots"


def positions_diagnose_dir() -> pathlib.Path:
    """Directory holding positions-diagnose output (``<base>/positions_diagnose``)."""
    return base_dir() / "positions_diagnose"


def coordinates_file() -> pathlib.Path:
    """Editable, user-managed station-coordinates CSV (``<base>/coordinates.csv``).

    Seeded on first use from the bundled ``resources/coordinates.csv`` — see
    :mod:`earthscope_positions.coordinates`.
    """
    return base_dir() / "coordinates.csv"

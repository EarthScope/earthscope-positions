"""Central resolver for the earthscope-positions data-directory layout.

The **base data directory** is resolved with this precedence:

    1. an explicit path set via :func:`set_base_dir`  (CLI ``--data-directory``)
    2. the ``ES_POS_DATA_DIRECTORY`` environment variable
    3. ``<project-root>/data``   (the default, i.e. ``./data``)

Every data sub-directory (``arrow/``, ``stream-lists/``, ``station-lists/``,
``plots/``, ``positions_diagnose/``, ``resources/``) derives from the base —
including the Arrow data root, which is always ``<base>/arrow``.

``resources/`` holds user-editable copies of bundled files — coordinates.csv
and the GeoJSON/MiniSEED export path-spec TOMLs — seeded from the package's
own ``resources/`` dir on first use (see :func:`ensure_resource`).

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


def bundled_resources_dir() -> pathlib.Path:
    """The package's bundled ``resources/`` dir — templates for coordinates.csv
    and the GeoJSON/MiniSEED export path-spec TOMLs, seeded into
    ``resources_dir()`` on first use by :func:`ensure_resource`.

    Tries the ``__file__``-relative path first (correct, and CWD-independent,
    for an *editable* install — this file then really does live under
    ``src/earthscope_positions/`` in the checkout, sibling to ``resources/``).
    Falls back to CWD-based (:func:`project_root`) for a real, non-editable
    install: that copies this module into site-packages, far from the
    checkout's top-level ``resources/`` — which isn't even part of the
    installed package (only ``src/earthscope_positions/`` is) — so it only
    resolves correctly when run with the repo checkout as CWD (e.g. the
    Docker image's WORKDIR). Same caveat webserver.py's ``_project_root`` hit
    for ``spa/spaBuild``, but that one has no CWD-independent fallback to
    prefer since the SPA build output was never __file__-adjacent to begin
    with.
    """
    file_relative = pathlib.Path(__file__).resolve().parents[2] / "resources"
    if file_relative.exists():
        return file_relative
    return project_root() / "resources"


def resources_dir() -> pathlib.Path:
    """User-editable copies of bundled resources (``<base>/resources``) —
    coordinates.csv and the export path-spec TOMLs."""
    return base_dir() / "resources"


def ensure_resource(name: str) -> pathlib.Path:
    """Return ``resources_dir()/<name>``, seeding it from the bundled
    ``resources/<name>`` template on first use.

    A no-op if the bundled template is itself missing (e.g. a non-editable
    install) — the returned path just won't exist yet, and it's up to the
    caller to handle that (coordinates.py falls back to an empty CSV; the
    export commands fall back to built-in spec defaults).
    """
    dst = resources_dir() / name
    if not dst.exists():
        src = bundled_resources_dir() / name
        if src.exists():
            import shutil
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dst)
    return dst


def coordinates_file() -> pathlib.Path:
    """Editable, user-managed station-coordinates CSV
    (``<base>/resources/coordinates.csv``).

    Seeded on first use from the bundled ``resources/coordinates.csv`` — see
    :mod:`earthscope_positions.coordinates`.
    """
    return resources_dir() / "coordinates.csv"


def geojson_spec_file() -> pathlib.Path:
    """Editable GeoJSON export path-spec TOML
    (``<base>/resources/geojson_path_spec.toml``)."""
    return resources_dir() / "geojson_path_spec.toml"


def miniseed_spec_file() -> pathlib.Path:
    """Editable MiniSEED export path-spec TOML
    (``<base>/resources/miniseed_path_spec.toml``)."""
    return resources_dir() / "miniseed_path_spec.toml"

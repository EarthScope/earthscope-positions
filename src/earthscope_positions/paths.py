"""Central resolver for the earthscope-positions data-directory layout.

The **base data directory** is resolved with this precedence:

    1. the ``ES_POS_DATA_DIRECTORY`` environment variable
    2. ``data_directory`` in the persisted config file
       (``~/.earthscope-positions.json`` — see :func:`config_path`)
    3. first run on a terminal: ask, then persist the answer to (2)
    4. otherwise the default, ``~/earthscope-positions``

Layer 1 is a per-invocation override (Docker, CI, cron); layer 2 is what makes
a choice stick across shells, which the environment variable does not.  When 1
is in play *and* disagrees with 2, :func:`base_dir` says so once — a silent
disagreement between "what I configured" and "what is actually being written"
is the kind of thing that gets noticed only after a long fetch lands in the
wrong place.

There is deliberately no ``--data-directory`` flag.  Having a third way to say
the same thing, on every data-touching subcommand, produced more confusion than
it resolved; the environment variable covers the same ground for the automated
callers that need a per-invocation override.  The webserver propagates its
resolved directory to child processes through the environment instead.

The config file also keeps ``known_data_directories``, the directories that
have been used before, so :func:`known_data_dirs` can offer them for switching
rather than making the user retype a path (``es-pos config use-data-dir``).

The prompt in layer 3 only fires when :func:`set_interactive` has been called
(the CLI does this for a TTY) — never in tests, in library use, or in the
subprocesses the webserver spawns, which inherit an explicit environment
variable anyway.  A non-interactive first run takes the default and prints
where it went.

Earlier versions defaulted to ``<nearest ancestor with pyproject.toml>/data``.
That is deliberately gone: run from inside an unrelated Python project, it
wrote a multi-GB tree into *that* project's directory.

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

import json
import os
import pathlib
import sys

ENV_VAR = "ES_POS_DATA_DIRECTORY"

#: Override for the config file location.  Mainly for tests, which must not
#: read (or write) the developer's real dotfile.
CONFIG_ENV_VAR = "ES_POS_CONFIG_FILE"

#: Single-file config in the user's home.  JSON rather than TOML because
#: ``tomllib`` is read-only -- the stdlib parses TOML but cannot write it, and
#: this file is written by ``es-pos config``, not by hand.
CONFIG_FILENAME = ".earthscope-positions.json"

#: Key holding the active data directory inside the config file.
CONFIG_DATA_DIR_KEY = "data_directory"

#: Key holding previously-used data directories, in the order they were first
#: seen.  Order is stable on purpose: ``es-pos config list-data-dirs`` numbers
#: them, and indices that shuffle on every switch would be useless to type.
CONFIG_KNOWN_DIRS_KEY = "known_data_directories"

#: Default when nothing is configured.  Deliberately visible and in $HOME:
#: this tree holds GB-scale Arrow data that users browse, export into, and
#: often want on a different volume -- not something to bury in an
#: application-support directory they cannot find.
DEFAULT_DATA_DIR_NAME = "earthscope-positions"

#: Set in the environment once the mismatch notice has been printed, so the
#: subprocesses the webserver spawns (which inherit it) stay quiet instead of
#: repeating the same notice into the web UI log on every export.
_MISMATCH_ENV_VAR = "ES_POS_CONFIG_MISMATCH_NOTIFIED"

_config_path_override: pathlib.Path | None = None
_interactive: bool = False
_resolved: tuple[pathlib.Path, str] | None = None


def project_root() -> pathlib.Path:
    """Nearest ancestor of the CWD containing pyproject.toml, else the CWD.

    No longer used for the data directory -- kept for locating checkout-relative
    assets (the built SPA, the README) in an editable install.
    """
    for p in [pathlib.Path.cwd(), *pathlib.Path.cwd().parents]:
        if (p / "pyproject.toml").exists():
            return p
    return pathlib.Path.cwd()


def reset_cache() -> None:
    """Forget the resolved data directory so the next lookup re-runs.

    Resolution is cached per process (see :func:`base_dir`); anything that
    changes an input -- the environment variable, the config file -- has to
    clear it.  Tests use this after monkeypatching the environment.
    """
    global _resolved
    _resolved = None


def set_config_path(path: "str | os.PathLike[str] | None") -> None:
    """Point the config file somewhere else (tests; ``None`` restores default)."""
    global _config_path_override, _resolved
    _config_path_override = pathlib.Path(path).expanduser() if path else None
    _resolved = None


def set_interactive(value: bool) -> None:
    """Allow (or forbid) prompting for the data directory on first run.

    The CLI enables this for a TTY.  Everything else -- tests, library callers,
    the webserver's child processes -- leaves it off, so a missing config can
    never block on stdin.
    """
    global _interactive
    _interactive = value


# ---------------------------------------------------------------------------
# Config file (~/.earthscope-positions.json)
# ---------------------------------------------------------------------------

def default_data_dir() -> pathlib.Path:
    """The built-in default data directory (``~/earthscope-positions``)."""
    return pathlib.Path.home() / DEFAULT_DATA_DIR_NAME


def config_path() -> pathlib.Path:
    """Location of the persisted config file.

    Lives in the user's home, *not* inside the installed package: it is created
    at runtime and survives upgrades, reinstalls, and uninstalls.
    """
    if _config_path_override is not None:
        return _config_path_override
    env = os.environ.get(CONFIG_ENV_VAR)
    if env:
        return pathlib.Path(env).expanduser()
    return pathlib.Path.home() / CONFIG_FILENAME


def read_config() -> dict:
    """Parse the config file; an empty dict if it is absent or unreadable.

    A corrupt config must not make the tool unusable -- it degrades to "not
    configured", which the caller can then fix with ``es-pos config``.
    """
    p = config_path()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (json.JSONDecodeError, OSError) as exc:
        print(f"[warn] Ignoring unreadable config {p}: {exc}", file=sys.stderr)
        return {}
    return data if isinstance(data, dict) else {}


def write_config(config: dict) -> pathlib.Path:
    """Write the config file, returning its path."""
    p = config_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    return p


def configured_data_dir() -> pathlib.Path | None:
    """The data directory recorded in the config file, if any."""
    raw = read_config().get(CONFIG_DATA_DIR_KEY)
    return pathlib.Path(str(raw)).expanduser() if raw else None


def known_data_dirs() -> list[pathlib.Path]:
    """Data directories that have been used before, in first-seen order.

    The active one is always included.  Entries are not validated here -- a
    directory can be missing (moved or deleted outside the tool) and callers
    are expected to show that rather than silently drop it.
    """
    raw = read_config().get(CONFIG_KNOWN_DIRS_KEY)
    if not isinstance(raw, list):
        raw = []
    out: list[pathlib.Path] = []
    for entry in raw:
        try:
            candidate = pathlib.Path(str(entry)).expanduser()
        except (TypeError, ValueError):
            continue
        if candidate not in out:
            out.append(candidate)
    active = configured_data_dir()
    if active is not None and active not in out:
        out.append(active)
    return out


def set_configured_data_dir(
    path: "str | os.PathLike[str]",
    *,
    remember: bool = True,
    drop: "str | os.PathLike[str] | None" = None,
) -> pathlib.Path:
    """Persist *path* as the active data directory.

    Other config keys are preserved.  Unless ``remember`` is false the path is
    appended to :data:`CONFIG_KNOWN_DIRS_KEY`, so it can be switched back to
    later without retyping.  ``drop`` removes a path from that history -- used
    by ``move-data-dir``, where the old location no longer exists and keeping
    it in the list would only offer a dead directory.
    """
    global _resolved
    resolved = pathlib.Path(path).expanduser().resolve()
    config = read_config()

    known = [str(p) for p in known_data_dirs()]
    if drop is not None:
        dead = str(pathlib.Path(drop).expanduser().resolve())
        known = [k for k in known if k != dead]
    if remember and str(resolved) not in known:
        known.append(str(resolved))

    config[CONFIG_DATA_DIR_KEY] = str(resolved)
    config[CONFIG_KNOWN_DIRS_KEY] = known
    write_config(config)
    _resolved = None
    return resolved


def forget_data_dir(path: "str | os.PathLike[str]") -> bool:
    """Drop *path* from the remembered list.  True if it was there.

    Refuses to forget the active directory -- the list would then no longer
    contain what is actually in use, which every display here assumes.
    """
    resolved = pathlib.Path(path).expanduser().resolve()
    active = configured_data_dir()
    if active is not None and active.resolve() == resolved:
        raise ValueError(
            f"{resolved} is the active data directory; switch to another one "
            f"before forgetting it."
        )
    known = [p for p in known_data_dirs()]
    remaining = [str(p) for p in known if p.resolve() != resolved]
    if len(remaining) == len(known):
        return False
    config = read_config()
    config[CONFIG_KNOWN_DIRS_KEY] = remaining
    write_config(config)
    return True


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------

def _notify_env_mismatch(active: pathlib.Path) -> None:
    """Point out that ``ES_POS_DATA_DIRECTORY`` disagrees with the config.

    Printed at most once per process tree: without it, a stale variable in a
    shell profile silently wins over the configured location for every command
    run from that shell.
    """
    configured = configured_data_dir()
    if configured is None or configured == active:
        return
    if os.environ.get(_MISMATCH_ENV_VAR):
        return
    print(
        f"[note] {ENV_VAR} is using {active}\n"
        f"       but {config_path()} says {configured}\n"
        f"       To make the configured location match, run:\n"
        f"         es-pos config set-data-dir {active}\n"
        f"       To use the configured location instead, unset {ENV_VAR}.",
        file=sys.stderr,
    )
    os.environ[_MISMATCH_ENV_VAR] = "1"


def _legacy_cwd_data_dir() -> pathlib.Path | None:
    """A pre-existing ``./data`` tree from the days of CWD-based resolution.

    Only reported, never adopted: silently picking it up would reinstate the
    CWD dependence this resolution order exists to remove.  Recognised by the
    sub-directories the tool itself creates, so an unrelated ``data/`` folder
    does not trigger it.
    """
    candidate = pathlib.Path.cwd() / "data"
    if not candidate.is_dir():
        return None
    if any((candidate / marker).is_dir() for marker in ("arrow", "stream-lists")):
        return candidate
    return None


def _legacy_hint(prefix: str = "") -> str:
    legacy = _legacy_cwd_data_dir()
    if legacy is None:
        return ""
    return (
        f"\n{prefix}Found an existing data directory at {legacy}.\n"
        f"{prefix}To keep using it:  es-pos config set-data-dir {legacy}"
    )


def _prompt_for_data_dir() -> pathlib.Path:
    """Ask where the data should live, then persist the answer."""
    default = default_data_dir()
    print(
        "\nearthscope-positions has no data directory configured yet.\n"
        "This is where downloaded position data is kept; it can grow to many GB,\n"
        "so pick a location with room (you can move it later with\n"
        "`es-pos config move-data-dir`)."
        + _legacy_hint(),
        file=sys.stderr,
    )
    try:
        reply = input(f"Data directory [{default}]: ").strip()
    except (EOFError, KeyboardInterrupt):
        print(file=sys.stderr)
        reply = ""
    chosen = pathlib.Path(reply).expanduser() if reply else default
    resolved = set_configured_data_dir(chosen)
    print(f"Saved to {config_path()}\n", file=sys.stderr)
    return resolved


def _resolve() -> tuple[pathlib.Path, str]:
    """Return (data directory, name of the layer that decided it)."""
    env = os.environ.get(ENV_VAR)
    if env:
        path = pathlib.Path(env).expanduser()
        _notify_env_mismatch(path)
        return path, "env"

    configured = configured_data_dir()
    if configured is not None:
        return configured, "config"

    if _interactive and sys.stdin.isatty():
        return _prompt_for_data_dir(), "prompt"

    default = default_data_dir()
    print(
        f"[note] No data directory configured; using {default}.\n"
        f"       Set one with: es-pos config set-data-dir PATH"
        + _legacy_hint("       "),
        file=sys.stderr,
    )
    return default, "default"


# ---------------------------------------------------------------------------
# Container awareness
# ---------------------------------------------------------------------------

#: Set by es-pos-docker.sh to the host side of the /data bind mount.  Its
#: presence also means "launched through the script", but only advisorily --
#: anyone can export it, so it is never treated as a guarantee.
HOST_DATA_DIR_ENV_VAR = "ES_POS_HOST_DATA_DIRECTORY"

#: Opt out of the "your data directory is not persistent" refusal, for a
#: deliberately throwaway container (a smoke test, a one-shot export to stdout).
ALLOW_EPHEMERAL_ENV_VAR = "ES_POS_ALLOW_EPHEMERAL_DATA"


def in_container() -> bool:
    """Best-effort "am I inside a container?".

    ``/.dockerenv`` is Docker's own marker; the cgroup scan additionally
    catches podman, containerd, and Kubernetes, which do not create it.
    """
    if pathlib.Path("/.dockerenv").exists():
        return True
    try:
        cgroup = pathlib.Path("/proc/1/cgroup").read_text(errors="replace")
    except OSError:
        return False
    return any(marker in cgroup for marker in ("docker", "containerd", "kubepods", "podman"))


def _mount_points(mountinfo: str) -> set[str]:
    """Mount points listed in /proc/self/mountinfo (field 5 of each line)."""
    points: set[str] = set()
    for line in mountinfo.splitlines():
        fields = line.split()
        if len(fields) >= 5:
            # Paths with spaces are octal-escaped in mountinfo.
            points.add(fields[4].replace("\\040", " "))
    return points


def data_dir_is_persistent(
    directory: "pathlib.Path | None" = None,
    mountinfo: "str | None" = None,
) -> "bool | None":
    """Is the data directory backed by a mount that outlives the container?

    True if the directory or an ancestor of it (excluding ``/``, which is the
    container's own ephemeral overlay) is a mount point.  ``None`` when it
    cannot be determined -- no ``/proc/self/mountinfo``, i.e. not Linux -- so
    callers can tell "not persistent" apart from "cannot tell".
    """
    if mountinfo is None:
        try:
            mountinfo = pathlib.Path("/proc/self/mountinfo").read_text(errors="replace")
        except OSError:
            return None
    directory = (directory or base_dir())
    try:
        resolved = directory.resolve()
    except OSError:
        resolved = directory
    mounts = _mount_points(mountinfo)
    for candidate in (resolved, *resolved.parents):
        if str(candidate) == "/":
            break
        if str(candidate) in mounts:
            return True
    return False


def container_data_dir_problems(
    directory: "pathlib.Path | None" = None,
    mountinfo: "str | None" = None,
) -> list[str]:
    """Fatal problems with the data directory inside a container.

    Only one thing is genuinely fatal: the data directory is not on a mount, so
    everything written to it dies with the container.  Being launched outside
    es-pos-docker.sh is *not* fatal -- docker-compose, Kubernetes and CI all
    mount correctly without it -- and could not be enforced anyway, since the
    variable the script sets can simply be exported by hand.
    """
    if not in_container():
        return []
    if os.environ.get(ALLOW_EPHEMERAL_ENV_VAR, "").strip() not in ("", "0", "false"):
        return []
    directory = directory or base_dir()
    persistent = data_dir_is_persistent(directory, mountinfo)
    if persistent is not False:
        return []                      # True, or None = cannot tell; do not block
    return [
        f"The data directory {directory} is inside the container's own filesystem, "
        f"not a mount.",
        "Everything written there — downloaded data, your lists, exports — is lost "
        "when the container stops.",
        "",
        "Start it with the launcher, which mounts a host directory:",
        "    ./es-pos-docker.sh run",
        "    ./es-pos-docker.sh run --data-dir /path/on/host",
        "",
        "Or mount one yourself:",
        f"    docker run -v /path/on/host:{directory} …",
        "",
        f"To run deliberately without persistence, set {ALLOW_EPHEMERAL_ENV_VAR}=1.",
    ]


def container_data_dir_notes(directory: "pathlib.Path | None" = None) -> list[str]:
    """Non-fatal observations about running in a container."""
    if not in_container():
        return []
    notes: list[str] = []
    if not os.environ.get(HOST_DATA_DIR_ENV_VAR):
        notes.append(
            "Running in a container but not through es-pos-docker.sh, so the host "
            "side of the data mount is unknown and the Overview tab cannot show it. "
            f"Set {HOST_DATA_DIR_ENV_VAR} to the host path if you want it displayed.")
    return notes


def base_dir() -> pathlib.Path:
    """Return the resolved base data directory (see module docstring).

    Resolution is cached per process so the prompt and the mismatch notice
    happen once, not on every path lookup.
    """
    global _resolved
    if _resolved is None:
        _resolved = _resolve()
    return _resolved[0]


def base_dir_source() -> str:
    """Which layer decided :func:`base_dir` -- one of
    ``flag`` / ``env`` / ``config`` / ``prompt`` / ``default``."""
    global _resolved
    if _resolved is None:
        _resolved = _resolve()
    return _resolved[1]


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


#: Path specs written before the data directory moved used CWD-relative roots
#: like "data/miniseed", back when the data directory itself was ./data.  That
#: leading segment is now redundant -- and actively wrong, since it would nest
#: the exports at <base>/data/miniseed.
_LEGACY_ROOT_PREFIX = "data"


def resolve_export_root(root: "str | os.PathLike[str]") -> pathlib.Path:
    """Resolve an export path-spec ``root`` to an absolute directory.

    An absolute root is honoured as-is.  A *relative* root is anchored to the
    data directory, never the current working directory -- anchoring to the CWD
    silently wrote exports next to wherever the command happened to be run
    from, which inside a container meant the image's own filesystem rather than
    the mounted data directory, so they vanished when it stopped.
    """
    path = pathlib.Path(root).expanduser()
    if path.is_absolute():
        return path
    parts = path.parts
    if parts and parts[0] == _LEGACY_ROOT_PREFIX:
        parts = parts[1:]          # "data/miniseed" -> "miniseed"
    return base_dir().joinpath(*parts) if parts else base_dir()


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

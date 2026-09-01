"""Which EarthScope deployment a data directory pulls from — prod or stage.

The two deployments are *not* interchangeable.  ``api.earthscope.org`` and
``api.dev.earthscope.org`` issue different EDIDs for the same physical
station, they need tokens from different ``es`` profiles, and a stream list
built against one is meaningless against the other.  Mixing them inside a
single Arrow tree produces data that looks fine and is silently wrong, so the
environment is a property of the **data directory**, not of the process, the
shell, or a per-command flag:

    <data directory>/.config/environment.json

Absence of that file means production.  That is deliberate — every directory
that existed before this file did is a production directory, and a directory
someone creates by hand stays production until an explicit act says otherwise.
The only such act is::

    es-pos config use-data-dir --stage DIR

which refuses to flip a directory that already holds data (see
:func:`describe_switch_conflict`) precisely so the two never mix in one tree.

Resolution order for the active environment:

    1. the ``ES_POS_ENVIRONMENT`` environment variable
    2. ``environment`` in ``<base>/.config/environment.json``
    3. ``prod``

Layer 1 exists so the webserver can hand its already-resolved answer to the
child ``es-pos`` processes it spawns, the same way it hands them
``ES_POS_DATA_DIRECTORY`` — not as a user-facing way to switch, which is why
no command sets it and no documentation offers it as one.

Every outbound API call routes through :func:`api_url` and :func:`profile`
rather than a module-level constant, so the two never drift apart.
"""
from __future__ import annotations

import dataclasses
import datetime as dt
import json
import os
import pathlib
import sys

from earthscope_positions import paths

#: Per-invocation override / propagation to child processes.  See module docs.
ENV_VAR = "ES_POS_ENVIRONMENT"

#: The earthscope-sdk's own profile variable.  When it is set explicitly it
#: wins over the environment's default profile — someone who has named their
#: stage profile something else should not have to rename it.
PROFILE_ENV_VAR = "ES_PROFILE"

#: Machinery directory inside the data directory.  Dot-prefixed and hidden
#: from the File Explorer: it is not data, and hand-editing it would route
#: around the switch guard that keeps prod and stage data apart.
CONFIG_DIR_NAME = ".config"

#: The marker file itself, inside :data:`CONFIG_DIR_NAME`.
ENV_FILE_NAME = "environment.json"


@dataclasses.dataclass(frozen=True)
class Environment:
    """One EarthScope deployment and everything that differs about it."""

    name: str
    """Short key — ``prod`` or ``stage``; what goes in the marker file."""

    label: str
    """Human-readable name for CLI output and the web UI badge."""

    api_url: str
    """Base URL for the REST API (SDK ``resources.api_url``)."""

    profile: str
    """Default ``es`` profile holding tokens for this deployment."""

    open_positions_url: "str | None"
    """Unauthenticated positions endpoint, used only by ``es-pos test fetch``.

    ``None`` where no such endpoint is known — the diagnostic then probes the
    authenticated endpoint alone rather than guessing at a hostname.
    """

    badge: bool
    """Whether the web UI should announce this environment.  Production is the
    unremarkable case and stays unlabelled; anything else gets a badge, so a
    tab pointed at stage can never be mistaken for one pointed at prod."""


PROD = Environment(
    name="prod",
    label="Production",
    api_url="https://api.earthscope.org",
    profile="default",
    open_positions_url="https://gnss-observations-api.prod.earthscope.org/positions/instantaneous/v2",
    badge=False,
)

STAGE = Environment(
    name="stage",
    label="Stage",
    # Stage is served from the *dev* domain; the name is ours, the hostname is
    # theirs.  Keeping our name for it means the marker files stay readable
    # even if the hostname moves again.
    api_url="https://api.dev.earthscope.org",
    profile="stage",
    # No dev equivalent of the prod open endpoint has been confirmed, and
    # guessing at one would turn `es-pos test fetch` into a DNS error.
    open_positions_url=None,
    badge=True,
)

ENVIRONMENTS: dict[str, Environment] = {e.name: e for e in (PROD, STAGE)}

DEFAULT_ENVIRONMENT = PROD.name

#: Cache key is every input to :func:`resolve`, so a test (or the webserver)
#: that changes the data directory or an environment variable mid-process gets
#: a fresh answer without having to know to clear anything.
_cache: "tuple[tuple, Environment, str] | None" = None


def reset_cache() -> None:
    """Forget the resolved environment (tests; after writing a marker)."""
    global _cache
    _cache = None


# ---------------------------------------------------------------------------
# Marker file
# ---------------------------------------------------------------------------

def config_dir(base: "pathlib.Path | None" = None) -> pathlib.Path:
    """``<base>/.config`` — per-data-directory machinery."""
    return (base or paths.base_dir()) / CONFIG_DIR_NAME


def marker_path(base: "pathlib.Path | None" = None) -> pathlib.Path:
    """``<base>/.config/environment.json``."""
    return config_dir(base) / ENV_FILE_NAME


def read_marker(base: "pathlib.Path | None" = None) -> dict:
    """Parse the marker file; an empty dict if absent or unreadable.

    Unreadable degrades to "production" rather than to an error: a corrupt
    marker must not make an existing production directory unusable, and the
    failure is loud enough on stderr to get fixed.
    """
    p = marker_path(base)
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (json.JSONDecodeError, OSError) as exc:
        print(f"[warn] Ignoring unreadable environment marker {p}: {exc}", file=sys.stderr)
        return {}
    return data if isinstance(data, dict) else {}


def marker_environment(base: "pathlib.Path | None" = None) -> "str | None":
    """The environment name recorded for *base*, or None if unmarked.

    An unrecognised name is reported as unknown rather than mapped to a
    default, so a directory written by a newer version does not get quietly
    treated as production and filled with the wrong EDIDs.
    """
    name = read_marker(base).get("environment")
    if not isinstance(name, str) or not name:
        return None
    return name


def environment_of(base: pathlib.Path) -> Environment:
    """The environment *base* is marked for — production when unmarked.

    Used to describe directories other than the active one (the numbered
    listing, the web UI's known-directories table).
    """
    return _lookup(marker_environment(base) or DEFAULT_ENVIRONMENT, source=str(base))


def write_marker(
    base: pathlib.Path, name: str, *, profile: "str | None" = None
) -> pathlib.Path:
    """Record *name* as the environment for the data directory *base*.

    The resolved ``profile`` and ``api_url`` are written alongside the name.
    They are not read back in preference to the built-in values by accident —
    :func:`resolve` honours them — so a directory keeps working against the
    endpoint it was actually filled from even if a future release changes what
    ``stage`` points at.

    ``profile`` overrides the environment's default profile name for this
    directory.  Worth having because the ``es`` profile that reaches a
    deployment is a per-install choice: someone whose dev credentials already
    live under a profile called ``dev`` should be able to point a stage
    directory at it rather than duplicate the entry under our preferred name.
    """
    env = _lookup(name, source="write_marker")
    if profile:
        env = dataclasses.replace(env, profile=profile)
    path = marker_path(base)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "environment": env.name,
                "profile": env.profile,
                "api_url": env.api_url,
                "written_at": dt.datetime.now(dt.timezone.utc)
                .replace(microsecond=0)
                .isoformat()
                .replace("+00:00", "Z"),
                "written_by": "es-pos config use-data-dir",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    reset_cache()
    return path


def configured_profiles() -> "list[str] | None":
    """Profile names defined in ``~/.earthscope/config.toml``.

    ``None`` when the file cannot be read at all, so callers can tell "no
    profiles" apart from "could not look".  Used only to turn the SDK's bare
    ``ProfileDoesNotExistError`` into a message that names the profiles that
    do exist — never to gate anything.
    """
    path = pathlib.Path.home() / ".earthscope" / "config.toml"
    try:
        import tomllib
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, ImportError):
        return None
    profiles = data.get("profile")
    if not isinstance(profiles, dict):
        return []
    return sorted(profiles)


def profile_setup_hint(prof: "str | None" = None) -> str:
    """Multi-line guidance for a profile the earthscope-sdk cannot find.

    The SDK's own error is just "Profile 'x' does not exist", which does not
    say where profiles live, what a working one looks like, or that this
    install may already have a suitable one under a different name — all three
    of which are the actual next step.
    """
    prof = prof or profile()
    env = current()
    config_toml = pathlib.Path.home() / ".earthscope" / "config.toml"
    existing = configured_profiles()
    lines = [
        f"The es profile '{prof}' needed for the {env.label} environment is not "
        f"defined in {config_toml}.",
    ]
    if existing:
        lines.append(f"  Profiles defined there: {', '.join(existing)}")
        lines.append(
            f"  If one of those already reaches {env.api_url}, point this data "
            f"directory at it:"
        )
        lines.append(
            f"    es-pos config use-data-dir --{env.name} --profile NAME "
            f"{paths.base_dir()}"
        )
    lines += [
        f"  Otherwise add a [profile.{prof}] section to {config_toml} with that "
        f"deployment's",
        f"  resources.api_url, oauth2.audience, oauth2.domain and oauth2.client_id, "
        f"then run:",
        f"    es user login --profile {prof}",
    ]
    return "\n".join(lines)


def _lookup(name: str, *, source: str) -> Environment:
    try:
        return ENVIRONMENTS[name]
    except KeyError:
        raise ValueError(
            f"Unknown environment {name!r} (from {source}); "
            f"expected one of: {', '.join(sorted(ENVIRONMENTS))}"
        ) from None


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------

def resolve() -> tuple[Environment, str]:
    """Return (environment, name of the layer that decided it).

    The layer is one of ``env`` / ``data-dir`` / ``default``.
    """
    global _cache
    base = paths.base_dir()
    key = (base, os.environ.get(ENV_VAR), os.environ.get(PROFILE_ENV_VAR))
    if _cache is not None and _cache[0] == key:
        return _cache[1], _cache[2]

    override = os.environ.get(ENV_VAR)
    if override:
        env, source = _lookup(override.strip(), source=ENV_VAR), "env"
    else:
        marked = marker_environment(base)
        if marked:
            env, source = _lookup(marked, source=str(marker_path(base))), "data-dir"
        else:
            env, source = ENVIRONMENTS[DEFAULT_ENVIRONMENT], "default"

    # Honour a marker that pins its own endpoint/profile (see write_marker).
    if source == "data-dir":
        raw = read_marker(base)
        overrides = {
            field: raw[field]
            for field in ("api_url", "profile")
            if isinstance(raw.get(field), str) and raw[field]
        }
        if overrides:
            env = dataclasses.replace(env, **overrides)

    _cache = (key, env, source)
    return env, source


def current() -> Environment:
    """The environment every API call in this process should use."""
    return resolve()[0]


def current_source() -> str:
    """Which layer decided :func:`current` — ``env`` / ``data-dir`` / ``default``."""
    return resolve()[1]


def name() -> str:
    """Short key of the active environment (``prod`` / ``stage``)."""
    return current().name


def label() -> str:
    """Human-readable name of the active environment."""
    return current().label


def is_default() -> bool:
    """True when the active environment is production."""
    return current().name == DEFAULT_ENVIRONMENT


def api_url() -> str:
    """Base REST API URL for the active environment."""
    return current().api_url


def profile() -> str:
    """``es`` profile whose tokens the active environment needs.

    An explicit ``ES_PROFILE`` wins: the environment supplies a *default*
    profile name, not a mandate, and someone whose stage tokens live under a
    differently-named profile should not have to rename it.
    """
    explicit = os.environ.get(PROFILE_ENV_VAR)
    if explicit and explicit.strip():
        return explicit.strip()
    return current().profile


def child_env() -> dict[str, str]:
    """Variables pinning this process's environment for a child ``es-pos``.

    Merged into the child's environment alongside ``ES_POS_DATA_DIRECTORY``.
    Both the environment name and the resolved profile go across, so a child
    cannot re-resolve to something different from its parent.
    """
    return {ENV_VAR: name(), PROFILE_ENV_VAR: profile()}


# ---------------------------------------------------------------------------
# Switching guard
# ---------------------------------------------------------------------------

#: Sub-directories whose presence means "this tree already holds data fetched
#: against whatever environment it was on".  Kept narrow on purpose: seeded
#: resources and generated plots carry no EDIDs and do not make a tree unsafe
#: to re-point.
_DATA_MARKERS = ("arrow", "stream-lists", "station-lists")


def directory_has_data(base: pathlib.Path) -> bool:
    """Does *base* already hold EDID-bearing data?"""
    for marker in _DATA_MARKERS:
        d = base / marker
        if not d.is_dir():
            continue
        try:
            if any(d.iterdir()):
                return True
        except OSError:
            continue
    return False


def describe_switch_conflict(base: pathlib.Path, to: str) -> "str | None":
    """Why *base* must not be re-pointed at environment *to*, or None if it may.

    Re-pointing a populated directory is the one way prod and stage data can
    end up in the same Arrow tree, where nothing downstream could tell them
    apart: the EDIDs differ, so the same station appears twice under unrelated
    identifiers and every stream list is half-valid.  Rather than merge them,
    refuse and point at a separate directory.
    """
    target = _lookup(to, source="switch")
    have = marker_environment(base) or DEFAULT_ENVIRONMENT
    if have == target.name:
        return None
    if not directory_has_data(base):
        return None
    current_env = ENVIRONMENTS.get(have)
    have_label = current_env.label if current_env else have
    return (
        f"{base}\n"
        f"  already holds {have_label} data, and {target.label} uses different "
        f"EDIDs for the same stations.\n"
        f"  Re-pointing it would mix the two in one Arrow tree with no way to "
        f"tell them apart.\n\n"
        f"  Use a separate directory instead:\n"
        f"    es-pos config use-data-dir --{target.name} ~/earthscope-positions-{target.name}"
    )

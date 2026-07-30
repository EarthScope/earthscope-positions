"""Shared pytest fixtures for earthscope-positions.

The whole point of this test suite is to exercise the code that talks to the
EarthScope API *without* touching the network, the VPN, or your on-disk
credentials.  There are two distinct API surfaces, and each is spoofed a
different way:

1.  Position data download (``earthscope_positions.fetch.positions_fetch``)
    calls the REST endpoint directly with the ``requests`` library.  We spoof
    it at the HTTP layer with the ``responses`` library — see the
    ``mock_positions_api`` fixture.

2.  Station discovery (``earthscope_positions.stations.station_list``) goes
    through the ``earthscope-sdk`` discovery service.  Rather than construct a
    real ``EarthScopeClient`` (which needs auth), we swap ``_discover()`` for a
    fake — see the ``fake_discover_api`` fixture.

Both surfaces also need an auth token; ``fake_token`` neutralises the real
credential/VPN lookup so no test ever shells out to ``es user login``.
"""
from __future__ import annotations

import datetime as dt
import io
from types import SimpleNamespace

import pyarrow as pa
import pyarrow.ipc as ipc
import pytest

from earthscope_positions import paths
from earthscope_positions.fetch import positions_fetch
from earthscope_positions.stations import station_list


@pytest.fixture(autouse=True)
def _reset_data_dir(monkeypatch):
    """Keep the data-directory resolution hermetic: no leaked env var or
    override from the developer's shell or a prior test."""
    monkeypatch.delenv(paths.ENV_VAR, raising=False)
    paths.set_base_dir(None)
    yield
    paths.set_base_dir(None)


# ---------------------------------------------------------------------------
# Working directory: give the code a real project root under tmp_path so that
# `_project_root()` / `_data_root()` resolve to an isolated, throwaway tree.
# ---------------------------------------------------------------------------


@pytest.fixture
def project_tree(tmp_path, monkeypatch):
    """chdir into an isolated project root (contains a pyproject.toml).

    ``positions_fetch`` and ``station_list`` both locate the project root by
    walking up from the CWD looking for ``pyproject.toml``, then read/write
    under ``<root>/data``.  Pointing that at a tmp dir keeps tests hermetic and
    lets us assert on the files they create.
    """
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'test'\n")
    (tmp_path / "data" / "arrow").mkdir(parents=True)
    (tmp_path / "data" / "stream-lists").mkdir(parents=True)
    monkeypatch.chdir(tmp_path)
    return tmp_path


# ---------------------------------------------------------------------------
# Auth: never read ~/.earthscope/tokens.json or shell out to the CLI.
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_token(monkeypatch):
    """Make ``_ensure_token()`` / ``_ensure_token_for_worker()`` return a dummy token.

    Only ``positions_fetch`` owns a token helper now; station discovery goes
    through the SDK client (faked separately), and the radial search imports
    ``positions_fetch._ensure_token`` at call time — so patching it here covers
    both the fetch path and radial search.  Worker threads re-check the token
    per task via ``_ensure_token_for_worker`` (see its docstring), so that must
    be patched too or a test would fall through to reading real credentials
    from disk.
    """
    monkeypatch.setattr(positions_fetch, "_ensure_token", lambda: "test-token")
    monkeypatch.setattr(positions_fetch, "_ensure_token_for_worker", lambda: "test-token")
    return "test-token"


# ---------------------------------------------------------------------------
# Arrow payload builder — produce bytes shaped exactly like the real API's
# ``application/vnd.apache.arrow.stream`` position response.
# ---------------------------------------------------------------------------


# Matches the schema the real positions endpoint returns.
POSITIONS_SCHEMA = pa.schema(
    [
        ("time", pa.int64()),          # epoch milliseconds
        ("east", pa.float64()),
        ("north", pa.float64()),
        ("up", pa.float64()),
        ("sigEE", pa.float64()),
        ("sigNN", pa.float64()),
        ("sigUU", pa.float64()),
        ("qChannel", pa.int64()),
        ("ingestLatency", pa.int64()),   # ms
        ("processingDelay", pa.int64()),  # ms
    ]
)


def make_positions_arrow(
    n_rows: int = 10,
    *,
    start: dt.datetime | None = None,
    step_ms: int = 1000,
    as_stream: bool = False,
) -> bytes:
    """Build Arrow IPC bytes with ``n_rows`` of synthetic 1 Hz position samples.

    Returns Arrow *file* format by default (what the real endpoint sends);
    pass ``as_stream=True`` to exercise the stream-format decode path.
    """
    if start is None:
        start = dt.datetime(2026, 1, 15, tzinfo=dt.timezone.utc)
    base_ms = int(start.timestamp() * 1000)
    times = [base_ms + i * step_ms for i in range(n_rows)]
    table = pa.table(
        {
            "time": times,
            "east": [0.001 * i for i in range(n_rows)],
            "north": [-0.001 * i for i in range(n_rows)],
            "up": [0.002 * i for i in range(n_rows)],
            "sigEE": [0.01] * n_rows,
            "sigNN": [0.01] * n_rows,
            "sigUU": [0.02] * n_rows,
            "qChannel": [0] * n_rows,
            "ingestLatency": [1500] * n_rows,
            "processingDelay": [200] * n_rows,
        },
        schema=POSITIONS_SCHEMA,
    )
    sink = io.BytesIO()
    opener = ipc.new_stream if as_stream else ipc.new_file
    with opener(sink, table.schema) as writer:
        writer.write_table(table)
    return sink.getvalue()


@pytest.fixture
def positions_arrow_bytes() -> bytes:
    """A ready-made Arrow payload (Arrow file format, 10 rows)."""
    return make_positions_arrow(10)


# ---------------------------------------------------------------------------
# Spoof #1 — the positions REST API (requests-based) via `responses`.
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_positions_api():
    """Intercept ``requests.get`` to the positions endpoint.

    Yields a ``responses.RequestsMock`` already scoped to the fetch module's
    ``requests`` object.  Register canned replies with::

        rsps.get(positions_fetch._API_BASE, body=arrow_bytes, status=200,
                 content_type="application/vnd.apache.arrow.stream")

    Any un-registered request raises, so tests can never silently hit the real
    API.  Import lazily so `responses` stays a test-only dependency.
    """
    import responses

    with responses.RequestsMock() as rsps:
        yield rsps


# ---------------------------------------------------------------------------
# Spoof #2 — the earthscope-sdk discovery service, via a fake.
# ---------------------------------------------------------------------------


def _fake_stream(rec):
    """A fake earthscope-sdk StreamDatasource.

    Mirrors the attributes station_list touches: ``.edid``, ``.names`` (a dict
    with a ``"GEOSNCL"`` key), and ``.facility`` / ``.software`` (plain strings).
    """
    return SimpleNamespace(
        edid=rec["edid"],
        names={"GEOSNCL": rec.get("geosncl")},
        facility=rec.get("facility"),
        software=rec.get("software"),
    )


def _fake_network(rec):
    """A fake earthscope-sdk NetworkDatasource — ``.names`` is a namespace dict,
    e.g. ``{"SHAKE": "NOTA"}``."""
    return SimpleNamespace(edid=rec.get("edid", ""), names=rec.get("names", {}))


class FakeDiscovery:
    """Stand-in for ``EarthScopeClient().discover`` (the SDK discovery service).

    Configure the replies before calling the code under test::

        fake.stream_records  = [{"edid", "geosncl", "facility", "software"}, ...]
        fake.network_records = [{"names": {"SHAKE": "NOTA"}}, ...]

    The SDK auto-paginates and returns a flat list, so these fakes return the
    full list in one call.  Recorded kwargs are on ``.stream_calls`` /
    ``.network_calls``.
    """

    def __init__(self):
        self.stream_records: list = []
        self.network_records: list = []
        self.stream_calls: list = []
        self.network_calls: list = []

    def list_stream_datasources(self, **kwargs):
        self.stream_calls.append(kwargs)
        return [_fake_stream(r) for r in self.stream_records]

    def list_network_datasources(self, **kwargs):
        self.network_calls.append(kwargs)
        return [_fake_network(r) for r in self.network_records]


@pytest.fixture
def fake_discover_api(monkeypatch):
    """Replace ``station_list._discover()`` with a configurable fake.

    Returns the ``FakeDiscovery`` instance so the test can set up replies and
    later inspect the recorded call kwargs.
    """
    fake = FakeDiscovery()
    monkeypatch.setattr(station_list, "_discover", lambda: fake)
    return fake

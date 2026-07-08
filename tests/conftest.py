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
    through the generated ``earthscope_client`` SDK (urllib3 under the hood).
    Rather than hand-craft SDK response models, we swap the API-client factory
    for a fake — see the ``fake_discover_api`` fixture.

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

from earthscope_client.models.facility import Facility
from earthscope_client.models.stream_software import StreamSoftware
from earthscope_positions.fetch import positions_fetch
from earthscope_positions.stations import station_list


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
    (tmp_path / "data" / "station-lists").mkdir(parents=True)
    monkeypatch.chdir(tmp_path)
    return tmp_path


# ---------------------------------------------------------------------------
# Auth: never read ~/.earthscope/tokens.json or shell out to the CLI.
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_token(monkeypatch):
    """Make ``_ensure_token()`` return a dummy token in both API modules."""
    monkeypatch.setattr(positions_fetch, "_ensure_token", lambda: "test-token")
    monkeypatch.setattr(station_list, "_ensure_token", lambda: "test-token")
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
# Spoof #2 — the station-discovery SDK, via a fake DiscoverApi.
# ---------------------------------------------------------------------------


def _stream_datasource_page(records, *, has_next=False):
    """Build a fake ``find_stream_datasources`` response.

    Mirrors only the attributes the caller touches:
    ``resp.actual_instance.items[*].{edid, names.geosncl, facility, software}``
    and ``resp.actual_instance.has_next``.  ``facility``/``software`` are real
    ``Facility``/``StreamSoftware`` enums, matching the SDK.
    """
    items = []
    for rec in records:
        fac = rec.get("facility")
        sw = rec.get("software")
        items.append(
            SimpleNamespace(
                edid=rec["edid"],
                names=SimpleNamespace(geosncl=rec.get("geosncl")),
                facility=Facility(fac) if fac is not None else None,
                software=StreamSoftware(sw) if sw is not None else None,
            )
        )
    page = SimpleNamespace(items=items, has_next=has_next)
    return SimpleNamespace(actual_instance=page)


def _radial_response(records):
    """Build a fake ``find_gnss_stations_radial`` response.

    ``resp.actual_instance`` is a list; each element exposes ``edid``,
    ``geosncl``, ``facility``, ``software`` as real SDK enums.
    """
    items = []
    for rec in records:
        fac = rec.get("facility")
        sw = rec.get("software")
        items.append(
            SimpleNamespace(
                edid=rec["edid"],
                geosncl=rec.get("geosncl"),
                facility=Facility(fac) if fac is not None else None,
                software=StreamSoftware(sw) if sw is not None else None,
            )
        )
    return SimpleNamespace(actual_instance=items)


class FakeDiscoverApi:
    """Stand-in for ``earthscope_client.api.discover_api.DiscoverApi``.

    Configure the replies before calling the code under test::

        fake.datasource_pages = [page1, page2]   # returned in order
        fake.radial_records = [...]

    Records are plain dicts: ``{"edid", "geosncl", "facility", "software"}``.
    """

    def __init__(self):
        self.datasource_pages: list = []
        self.radial_records: list = []
        self.datasource_calls: list = []
        self.radial_calls: list = []
        self._page_idx = 0

    # -- mirrors DiscoverApi.find_stream_datasources -----------------------
    def find_stream_datasources(self, **kwargs):
        self.datasource_calls.append(kwargs)
        if self._page_idx >= len(self.datasource_pages):
            return _stream_datasource_page([], has_next=False)
        records, has_next = self.datasource_pages[self._page_idx]
        self._page_idx += 1
        return _stream_datasource_page(records, has_next=has_next)

    # -- mirrors DiscoverApi.find_gnss_stations_radial ---------------------
    def find_gnss_stations_radial(self, **kwargs):
        self.radial_calls.append(kwargs)
        return _radial_response(self.radial_records)


@pytest.fixture
def fake_discover_api(monkeypatch):
    """Replace ``station_list._make_api`` with a configurable fake.

    Returns the ``FakeDiscoverApi`` instance so the test can set up replies
    and later inspect the recorded call kwargs.
    """
    fake = FakeDiscoverApi()
    monkeypatch.setattr(station_list, "_make_api", lambda token: fake)
    return fake

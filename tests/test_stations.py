"""Tests for station discovery — now backed by the earthscope-sdk.

- Datasource / network discovery goes through ``EarthScopeClient().discover``;
  the ``fake_discover_api`` fixture swaps ``station_list._discover()`` for a
  configurable fake, so no network / auth is needed.
- Radial search has no SDK equivalent, so ``station_list._get_radial`` calls the
  REST endpoint directly; those tests intercept it with ``responses`` and use
  ``fake_token`` for the bearer token.
"""
from __future__ import annotations

import responses

from earthscope_positions.stations import station_list


class _Namespace:
    def __init__(self, **kw):
        self.__dict__.update(kw)


# ---------------------------------------------------------------------------
# get datasource
# ---------------------------------------------------------------------------


def test_get_datasource_returns_records(fake_discover_api):
    fake_discover_api.stream_records = [
        {"edid": "E1", "geosncl": "P100.CI.LY_.20", "facility": "caltech", "software": "jpl_ppp"},
        {"edid": "E2", "geosncl": "P101.PB.LY_.20", "facility": "cwu", "software": "jpl_ppp"},
    ]

    args = _Namespace(
        station_name=None, facility=None, software=None,
        label=None, network_name=["SHAKE:ShakeAlert"],
    )
    records = station_list._get_datasource(args)

    assert [r["edid"] for r in records] == ["E1", "E2"]
    assert records[0]["geosncl"] == "P100.CI.LY_.20"
    assert records[0]["facility"] == "caltech"    # plain string now, not an enum
    assert records[0]["software"] == "jpl_ppp"


def test_get_datasource_single_call(fake_discover_api):
    """The SDK auto-paginates, so discovery is a single call returning all rows."""
    fake_discover_api.stream_records = [
        {"edid": f"E{i}", "geosncl": f"P10{i}.CI.LY_.20"} for i in range(5)
    ]
    args = _Namespace(
        station_name=None, facility=None, software=None, label=None, network_name=None,
    )
    records = station_list._get_datasource(args)

    assert len(records) == 5
    assert len(fake_discover_api.stream_calls) == 1


def test_get_datasource_forwards_filters(fake_discover_api):
    fake_discover_api.stream_records = []

    args = _Namespace(
        station_name=None, facility="caltech", software="jpl_ppp",
        label="mylabel", network_name=["SHAKE:NOTA"],
    )
    station_list._get_datasource(args)

    call = fake_discover_api.stream_calls[0]
    assert call["stream_type"] == station_list.StreamType.GNSS_PPP
    assert call["facility"] == "caltech"       # strings, not enums
    assert call["software"] == "jpl_ppp"
    assert call["label"] == "mylabel"
    assert call["network_name"] == ["SHAKE:NOTA"]


# ---------------------------------------------------------------------------
# networks + network_geosncls
# ---------------------------------------------------------------------------


def test_list_networks_filters_namespaces(fake_discover_api):
    fake_discover_api.network_records = [
        {"names": {"SHAKE": "NOTA"}},
        {"names": {"RTDB": "PBO"}},
        {"names": {"FDSN": "PB"}},          # not RTDB/SHAKE → excluded
        {"names": {"SHAKE": "ORGN", "FDSN": "X"}},
    ]
    nets = station_list.list_networks()
    assert nets == ["RTDB:PBO", "SHAKE:NOTA", "SHAKE:ORGN"]


def test_network_geosncls(fake_discover_api):
    fake_discover_api.stream_records = [
        {"edid": "E1", "geosncl": "P100.CI.LY_.30"},
        {"edid": "E2", "geosncl": "P101.PB.LY_.30"},
        {"edid": "E3", "geosncl": None},     # no geosncl → skipped
    ]
    out = station_list.network_geosncls("SHAKE:ORGN")
    assert out == ["P100.CI.LY_.30", "P101.PB.LY_.30"]
    assert fake_discover_api.stream_calls[0]["network_name"] == "SHAKE:ORGN"
    assert fake_discover_api.stream_calls[0]["stream_type"] == station_list.StreamType.GNSS_PPP


# ---------------------------------------------------------------------------
# get radial (direct REST — no SDK method)
# ---------------------------------------------------------------------------

# Resolved inside each test, not at import: _api_host() reads the active
# environment, which the autouse data-directory fixture has not set up yet
# at collection time.
def _radial_url() -> str:
    return f"{station_list._api_host()}/beta/discover/gnss/radial"


def test_get_radial_returns_records(fake_token):
    body = [
        {"edid": "E1", "geosncl": "P100.CI.LY_.20", "facility": "caltech", "software": "jpl_ppp"},
        {"edid": "E2", "geosncl": "P101.PB.LY_.20", "facility": "cwu", "software": "jpl_ppp"},
    ]
    args = _Namespace(
        latitude=37.5, longitude=-122.0, distance=100.0,
        network_name=None, facility=None, software=None,
    )
    with responses.RequestsMock() as rsps:
        rsps.get(_radial_url(), json=body, status=200)
        records = station_list._get_radial(args)
        req = rsps.calls[0].request

    assert [r["edid"] for r in records] == ["E1", "E2"]
    assert "stream_type=gnss_ppp" in req.url
    assert "tier=stream" in req.url
    assert req.headers["authorization"] == "Bearer test-token"


def test_get_radial_filters_by_software_locally(fake_token):
    body = [
        {"edid": "E1", "geosncl": "P100.CI.LY_.20", "software": "jpl_ppp"},
        {"edid": "E2", "geosncl": "P101.PB.LY_.20", "software": "rtnet"},
    ]
    args = _Namespace(
        latitude=37.5, longitude=-122.0, distance=100.0,
        network_name=None, facility=None, software="jpl_ppp",
    )
    with responses.RequestsMock() as rsps:
        rsps.get(_radial_url(), json=body, status=200)
        records = station_list._get_radial(args)

    assert [r["edid"] for r in records] == ["E1"]

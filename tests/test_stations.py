"""Tests for station discovery — the SDK's DiscoverApi is spoofed via a fake.

``station_list`` talks to the EarthScope API through the generated
``earthscope_client`` SDK.  The ``fake_discover_api`` fixture replaces the
API-client factory (``_make_api``) with a configurable stand-in, and
``fake_token`` neutralises the credential lookup, so these tests run with no
network, no VPN, and no on-disk tokens.
"""
from __future__ import annotations

from earthscope_positions.stations import station_list


class _Namespace:
    def __init__(self, **kw):
        self.__dict__.update(kw)


# ---------------------------------------------------------------------------
# get datasource
# ---------------------------------------------------------------------------


def test_get_datasource_single_page(fake_token, fake_discover_api):
    fake_discover_api.datasource_pages = [
        (
            [
                {"edid": "E1", "geosncl": "P100.CI.LY_.20",
                 "facility": "caltech", "software": "jpl_ppp"},
                {"edid": "E2", "geosncl": "P101.PB.LY_.20",
                 "facility": "cwu", "software": "jpl_ppp"},
            ],
            False,  # has_next
        ),
    ]

    args = _Namespace(
        station_name=None, facility=None, software=None,
        label=None, network_name=["SHAKE:ShakeAlert"],
    )
    records = station_list._get_datasource(args)

    assert [r["edid"] for r in records] == ["E1", "E2"]
    assert records[0]["geosncl"] == "P100.CI.LY_.20"
    assert records[0]["facility"] == "caltech"
    assert records[0]["software"] == "jpl_ppp"


def test_get_datasource_paginates(fake_token, fake_discover_api):
    """The command should keep requesting pages while ``has_next`` is True."""
    fake_discover_api.datasource_pages = [
        ([{"edid": "E1", "geosncl": "P100.CI.LY_.20"}], True),
        ([{"edid": "E2", "geosncl": "P101.CI.LY_.20"}], True),
        ([{"edid": "E3", "geosncl": "P102.CI.LY_.20"}], False),
    ]

    args = _Namespace(
        station_name=None, facility=None, software=None,
        label=None, network_name=None,
    )
    records = station_list._get_datasource(args)

    assert [r["edid"] for r in records] == ["E1", "E2", "E3"]
    assert len(fake_discover_api.datasource_calls) == 3
    # Offsets should advance by the page size.
    offsets = [c["offset"] for c in fake_discover_api.datasource_calls]
    assert offsets == [0, station_list._PAGE_SIZE, 2 * station_list._PAGE_SIZE]


def test_get_datasource_forwards_filters(fake_token, fake_discover_api):
    fake_discover_api.datasource_pages = [([], False)]

    args = _Namespace(
        station_name=None, facility="caltech", software="jpl_ppp",
        label="mylabel", network_name=["SHAKE:NOTA"],
    )
    station_list._get_datasource(args)

    call = fake_discover_api.datasource_calls[0]
    assert call["stream_type"] == station_list.StreamType.GNSS_PPP
    assert call["facility"] == station_list.Facility("caltech")
    assert call["software"] == station_list.StreamSoftware("jpl_ppp")
    assert call["label"] == "mylabel"
    assert call["network_name"] == ["SHAKE:NOTA"]


# ---------------------------------------------------------------------------
# get radial
# ---------------------------------------------------------------------------


def test_get_radial_returns_records(fake_token, fake_discover_api):
    fake_discover_api.radial_records = [
        {"edid": "E1", "geosncl": "P100.CI.LY_.20",
         "facility": "caltech", "software": "jpl_ppp"},
        {"edid": "E2", "geosncl": "P101.PB.LY_.20",
         "facility": "cwu", "software": "jpl_ppp"},
    ]

    args = _Namespace(
        latitude=37.5, longitude=-122.0, distance=100.0,
        network_name=None, facility=None, software=None,
    )
    records = station_list._get_radial(args)

    assert [r["edid"] for r in records] == ["E1", "E2"]
    call = fake_discover_api.radial_calls[0]
    assert call["latitude"] == 37.5
    assert call["distance"] == 100.0
    assert call["tier"] == station_list.ReferencePositionTier.STREAM


def test_get_radial_filters_by_software_locally(fake_token, fake_discover_api):
    """--software is applied client-side after the radial call."""
    fake_discover_api.radial_records = [
        {"edid": "E1", "geosncl": "P100.CI.LY_.20", "software": "jpl_ppp"},
        {"edid": "E2", "geosncl": "P101.PB.LY_.20", "software": "rtnet"},
    ]

    args = _Namespace(
        latitude=37.5, longitude=-122.0, distance=100.0,
        network_name=None, facility=None, software="jpl_ppp",
    )
    records = station_list._get_radial(args)

    assert [r["edid"] for r in records] == ["E1"]

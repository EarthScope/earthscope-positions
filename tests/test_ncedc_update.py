"""Update ShakeAlert Partner Streams — the NCEDC metadata refresh.

The two things that actually broke here: which files the index scan picks up,
and parsing the coordinate file that sits beside them.
"""
from __future__ import annotations

import re

import pytest

from earthscope_positions.webserver import webserver as w


# Exactly what ncedc.org/outgoing/gps/ShakeAlert/metadata/ lists.
_INDEX_HTML = """
<html><body><h1>Index of /outgoing/gps/ShakeAlert/metadata</h1>
<a href="README">README</a>
<a href="STAGE/">STAGE/</a>
<a href="chanfile_bk.dat">chanfile_bk.dat</a>
<a href="chanfile_ci.dat">chanfile_ci.dat</a>
<a href="chanfile_nc.dat">chanfile_nc.dat</a>
<a href="chanfile_pb.dat">chanfile_pb.dat</a>
<a href="chanfile_pw.dat">chanfile_pw.dat</a>
<a href="exclude.dat">exclude.dat</a>
<a href="merged_chanfile_coord.dat">merged_chanfile_coord.dat</a>
<a href="station_coords.dat">station_coords.dat</a>
<a href="station_coords_extended.dat">station_coords_extended.dat</a>
</body></html>
"""

_CHANFILE_RE = r'(?<![A-Za-z0-9_-])chanfile_(\w+)\.dat'


def _codes(html: str) -> list[str]:
    return sorted(set(re.findall(_CHANFILE_RE, html)))


# ---------------------------------------------------------------------------
# Index scan
# ---------------------------------------------------------------------------

def test_only_real_partner_networks_are_matched():
    assert _codes(_INDEX_HTML) == ["bk", "ci", "nc", "pb", "pw"]


def test_merged_chanfile_coord_does_not_produce_a_network():
    """The unanchored pattern matched inside merged_chanfile_coord.dat and
    produced a 'coord' network, then 404ed fetching chanfile_coord.dat."""
    assert "coord" not in _codes(_INDEX_HTML)
    assert _codes('<a href="merged_chanfile_coord.dat">x</a>') == []


def test_the_pattern_the_server_uses_is_the_anchored_one():
    """Guards against the anchor being dropped during a future edit."""
    import inspect
    src = inspect.getsource(w.api_update_active_from_ncedc)
    assert "(?<![A-Za-z0-9_-])chanfile_" in src


@pytest.mark.parametrize("name,expected", [
    ("chanfile_bk.dat", ["bk"]),
    ("merged_chanfile_coord.dat", []),
    ("x_chanfile_zz.dat", []),
    ("station_coords_extended.dat", []),
])
def test_pattern_cases(name, expected):
    assert _codes(f'<a href="{name}">{name}</a>') == expected


# ---------------------------------------------------------------------------
# station_coords_extended.dat
# ---------------------------------------------------------------------------

_COORDS_DAT = """\
# IGb14 COORDINATES OF SHAKEALERT GPS NETWORK MONUMENTS
#
# Maintained by someone@usgs.gov
#
    7ODM    34.11640841  -117.09319797    761.9103    -2407751.26650 -4706536.26910  3557571.44044    2026.0055
    ACSB    33.27426670  -117.44489595    -12.4067    -2460183.88354 -4737087.11138  3479422.82508    2026.0055
    agmt    34.59428095  -116.42938252   1337.7923    -2339956.63906 -4707748.65579  3601665.98332    2026.0055
"""


def test_coords_parse_to_csv():
    csv_text, n, bad = w._shakealert_coords_to_csv(_COORDS_DAT)
    assert (n, bad) == (3, 0)
    lines = csv_text.splitlines()
    assert lines[0] == "station,latitude,longitude,height,source"
    assert lines[1] == "7ODM,34.11640841,-117.09319797,761.9103,shakealert"


def test_station_codes_are_upper_cased():
    csv_text, _, _ = w._shakealert_coords_to_csv(_COORDS_DAT)
    assert any(l.startswith("AGMT,") for l in csv_text.splitlines())


def test_comments_and_blanks_are_not_counted_as_bad_rows():
    _, n, bad = w._shakealert_coords_to_csv("# just a comment\n\n\n")
    assert (n, bad) == (0, 0)


def test_malformed_rows_are_counted_not_fatal():
    text = _COORDS_DAT + "  SHORT 1.0\n  BADNUM x y z\n"
    csv_text, n, bad = w._shakealert_coords_to_csv(text)
    assert n == 3 and bad == 2
    assert "SHORT" not in csv_text and "BADNUM" not in csv_text


def test_output_is_accepted_by_the_coordinates_merger(project_tree):
    """The CSV has to satisfy the same validator an uploaded file does.

    These three stations are already in the bundled coordinates table, so they
    come back as updates rather than additions -- what matters is that all
    three land, with the NCEDC values winning.
    """
    from earthscope_positions import coordinates as c
    csv_text, _, _ = w._shakealert_coords_to_csv(_COORDS_DAT)
    total, added, updated = c.merge_upload(csv_text)
    assert added + updated >= 3
    assert total >= 3

    coords = c.Coordinates()
    for station in ("7ODM", "ACSB", "AGMT"):
        assert coords.get(station) is not None, station
    seven = coords.get("7ODM")
    assert seven.source == "shakealert"
    assert seven.latitude == pytest.approx(34.11640841)
    assert seven.longitude == pytest.approx(-117.09319797)


def test_merger_adds_stations_it_has_never_seen(project_tree):
    from earthscope_positions import coordinates as c
    novel = ("station,latitude,longitude,height,source\n"
             "ZZ99,10.5,-20.25,100.0,shakealert\n")
    _, added, _ = c.merge_upload(novel)
    assert added == 1
    assert c.Coordinates().get("ZZ99").source == "shakealert"

"""Import sanity + fixture wiring checks.

If the editable install is mis-configured (e.g. after moving the repo, the
``__editable__.*.pth`` under the venv still points at the old path) these will
fail fast with a clear message rather than a confusing error deep in a test.
"""
from __future__ import annotations


def test_package_imports():
    import earthscope_positions  # noqa: F401
    from earthscope_positions.fetch import positions_fetch  # noqa: F401
    from earthscope_positions.stations import station_list  # noqa: F401


def test_sdk_client_imports():
    from earthscope_sdk import EarthScopeClient  # noqa: F401
    from earthscope_sdk.client.discovery.models import StreamType  # noqa: F401


def test_arrow_helper_roundtrips():
    from conftest import make_positions_arrow
    from earthscope_positions.fetch import positions_fetch

    tbl = positions_fetch._read_arrow_bytes(make_positions_arrow(7))
    assert tbl is not None and tbl.num_rows == 7
    assert "time" in tbl.schema.names

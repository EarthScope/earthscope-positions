"""Stream-list record validation and the all-streams protection.

A stream record without `edid` cannot be fetched — the API is queried by EDID
and a geosncl does not parse as one — so an incomplete record fails silently as
"no data" much later. These rules move that failure to the point of writing.
"""
from __future__ import annotations

import json

import pytest

from earthscope_positions import paths
from earthscope_positions.stations import station_list as sl

GOOD = {
    "geosncl": "HELP.BK.LY_.30",
    "edid": "01H46MV57FWRWQM3HQBQVTJ1RK",
    "facility": "ucb",
    "software": "septentrio_onboard",
}


@pytest.fixture
def client(project_tree):
    from fastapi.testclient import TestClient
    import earthscope_positions.webserver.webserver as w
    return TestClient(w.app)


@pytest.fixture
def with_all_streams(project_tree):
    """An all-streams reference containing GOOD plus one more."""
    other = {**GOOD, "geosncl": "OTHR.BK.LY_.30", "edid": "01H46MV57FWRWQM3HQBQVTJ1RX"}
    d = paths.stream_lists_dir()
    d.mkdir(parents=True, exist_ok=True)
    (d / "all-streams.jsonl").write_text(
        json.dumps(GOOD) + "\n" + json.dumps(other) + "\n")
    return [GOOD, other]


# ---------------------------------------------------------------------------
# Record shape
# ---------------------------------------------------------------------------

def test_the_documented_shape_validates():
    assert sl.validate_stream_record(GOOD) is None


@pytest.mark.parametrize("field", ["geosncl", "edid", "facility", "software"])
def test_every_field_is_required(field):
    rec = {k: v for k, v in GOOD.items() if k != field}
    assert field in sl.validate_stream_record(rec)


@pytest.mark.parametrize("field", ["geosncl", "edid", "facility", "software"])
def test_empty_fields_are_rejected(field):
    assert field in sl.validate_stream_record({**GOOD, field: "  "})


def test_unexpected_fields_are_rejected():
    assert "unexpected" in sl.validate_stream_record({**GOOD, "notes": "hi"})


def test_non_object_lines_are_rejected():
    assert "JSON object" in sl.validate_stream_record(["a", "b"])


@pytest.mark.parametrize("geosncl", [
    "BAD", "A.B.C", "A.B.C.D.E", "GEOSNCL:AGNS.NC.LY_.20.X", ".B.C.D",
])
def test_malformed_geosncl_is_rejected(geosncl):
    assert sl.validate_stream_record({**GOOD, "geosncl": geosncl}) is not None


def test_duplicate_geosncls_are_reported():
    text = json.dumps(GOOD) + "\n" + json.dumps(GOOD) + "\n"
    errors = sl.validate_stream_list_text(text)
    assert any("duplicate" in e for e in errors)


def test_membership_in_all_streams_is_enforced():
    text = json.dumps(GOOD) + "\n"
    assert sl.validate_stream_list_text(text, {"SOME.OTHER.LY_.00"})
    assert sl.validate_stream_list_text(text, {GOOD["geosncl"]}) == []


# ---------------------------------------------------------------------------
# Editing through the API
# ---------------------------------------------------------------------------

def test_valid_content_saves(client, with_all_streams):
    r = client.post("/api/stream-lists/mine/raw", json={"content": json.dumps(GOOD) + "\n"})
    assert r.status_code == 200
    assert (paths.stream_lists_dir() / "mine.jsonl").exists()


def test_incomplete_record_is_rejected(client, with_all_streams):
    r = client.post("/api/stream-lists/mine/raw",
                    json={"content": '{"geosncl": "HELP.BK.LY_.30"}\n'})
    assert r.status_code == 400
    assert "edid" in r.json()["error"]
    assert not (paths.stream_lists_dir() / "mine.jsonl").exists()


def test_stream_absent_from_all_streams_is_rejected(client, with_all_streams):
    stray = {**GOOD, "geosncl": "NOPE.XX.LY_.99"}
    r = client.post("/api/stream-lists/mine/raw", json={"content": json.dumps(stray) + "\n"})
    assert r.status_code == 400
    assert "all-streams" in r.json()["error"]


def test_error_names_the_offending_line(client, with_all_streams):
    content = json.dumps(GOOD) + "\n" + '{"geosncl": "HELP.BK.LY_.30"}\n'
    r = client.post("/api/stream-lists/mine/raw", json={"content": content})
    assert "line 2" in r.json()["error"]


# ---------------------------------------------------------------------------
# all-streams is protected
# ---------------------------------------------------------------------------

def test_protected_list_is_advertised(client, with_all_streams):
    assert client.get("/api/stream-lists/protected").json()["protected"] == ["all-streams"]


@pytest.mark.parametrize("call", [
    lambda c: c.post("/api/stream-lists/all-streams/raw", json={"content": ""}),
    lambda c: c.delete("/api/stream-lists/all-streams"),
    lambda c: c.post("/api/stream-lists/all-streams/rename", json={"new_name": "x"}),
])
def test_all_streams_cannot_be_changed(client, with_all_streams, call):
    assert call(client).status_code == 403


def test_nothing_can_be_renamed_onto_all_streams(client, with_all_streams):
    client.post("/api/stream-lists/mine/raw", json={"content": json.dumps(GOOD) + "\n"})
    r = client.post("/api/stream-lists/mine/rename", json={"new_name": "all-streams"})
    assert r.status_code == 403


def test_all_streams_survives_a_blocked_delete(client, with_all_streams):
    client.delete("/api/stream-lists/all-streams")
    assert (paths.stream_lists_dir() / "all-streams.jsonl").exists()


# ---------------------------------------------------------------------------
# Loading reports what it dropped
# ---------------------------------------------------------------------------

def test_load_filters_incomplete_records_and_counts_them(client, with_all_streams):
    (paths.stream_lists_dir() / "legacy.jsonl").write_text(
        json.dumps(GOOD) + "\n"
        '{"geosncl": "OTHR.BK.LY_.30", "edid": "01H46MV57FWRWQM3HQBQVTJ1RX"}\n'
        '{"geosncl": "THRD.BK.LY_.30"}\n')
    body = client.get("/api/stream-lists/legacy").json()
    assert body["total"] == 3
    assert body["filtered"] == 2
    assert body["geosncls"] == [GOOD["geosncl"]]
    assert len(body["filtered_reasons"]) == 2


def test_load_of_a_clean_list_reports_nothing_filtered(client, with_all_streams):
    body = client.get("/api/stream-lists/all-streams").json()
    assert body["filtered"] == 0
    assert body["protected"] is True


# ---------------------------------------------------------------------------
# The structured save must not create the problem it now rejects
# ---------------------------------------------------------------------------

def test_structured_save_writes_complete_records(client, with_all_streams):
    r = client.post("/api/stream-lists/built",
                    json={"geosncls": [GOOD["geosncl"], "OTHR.BK.LY_.30"]})
    assert r.json()["count"] == 2
    for line in (paths.stream_lists_dir() / "built.jsonl").read_text().splitlines():
        assert sl.validate_stream_record(json.loads(line)) is None


def test_structured_save_skips_unknown_streams_and_reports(client, with_all_streams):
    r = client.post("/api/stream-lists/built",
                    json={"geosncls": [GOOD["geosncl"], "GHOST.XX.LY_.00"]})
    body = r.json()
    assert body["count"] == 1
    assert body["skipped"] == 1
    assert body["skipped_geosncls"] == ["GHOST.XX.LY_.00"]


def test_a_saved_list_round_trips_through_the_editor(client, with_all_streams):
    """What Save writes must pass the validator Save-As applies."""
    client.post("/api/stream-lists/built", json={"geosncls": [GOOD["geosncl"]]})
    content = client.get("/api/stream-lists/built/raw").json()["content"]
    assert client.post("/api/stream-lists/built/raw",
                       json={"content": content}).status_code == 200


# ---------------------------------------------------------------------------
# es-pos lists validate-streams
# ---------------------------------------------------------------------------

def _run(*argv: str) -> None:
    import sys
    from earthscope_positions.stations import station_list
    old = sys.argv
    sys.argv = ["es-pos lists", *argv]
    try:
        station_list.main()
    finally:
        sys.argv = old


def test_validate_passes_on_clean_lists(with_all_streams, capsys):
    (paths.stream_lists_dir() / "clean.jsonl").write_text(json.dumps(GOOD) + "\n")
    _run("validate-streams", "clean")
    assert "All 1 list(s) valid" in capsys.readouterr().out


def test_validate_exits_nonzero_on_problems(with_all_streams):
    (paths.stream_lists_dir() / "broken.jsonl").write_text('{"geosncl": "HELP.BK.LY_.30"}\n')
    with pytest.raises(SystemExit) as exc:
        _run("validate-streams", "broken")
    assert exc.value.code == 1


def test_validate_checks_every_list_by_default(with_all_streams, capsys):
    (paths.stream_lists_dir() / "broken.jsonl").write_text('{"geosncl": "HELP.BK.LY_.30"}\n')
    with pytest.raises(SystemExit):
        _run("validate-streams")
    out = capsys.readouterr().out
    assert "broken" in out and "all-streams" in out


def test_all_streams_is_not_checked_against_itself(with_all_streams, capsys):
    """Membership of the reference in itself is circular; it must still pass."""
    _run("validate-streams", "all-streams")
    assert "OK" in capsys.readouterr().out


def test_fix_repairs_from_all_streams_without_losing_records(with_all_streams, capsys):
    """The real-world case: records complete but for facility/software, which
    all-streams has. Repair beats discard -- dropping would empty the list."""
    partial = {"geosncl": GOOD["geosncl"], "edid": GOOD["edid"]}
    other = {"geosncl": "OTHR.BK.LY_.30", "edid": "01H46MV57FWRWQM3HQBQVTJ1RX"}
    path = paths.stream_lists_dir() / "legacy.jsonl"
    path.write_text(json.dumps(partial) + "\n" + json.dumps(other) + "\n")

    with pytest.raises(SystemExit):
        _run("validate-streams", "legacy", "--fix")

    lines = [json.loads(l) for l in path.read_text().splitlines() if l.strip()]
    assert len(lines) == 2, "no record should have been dropped"
    for rec in lines:
        assert sl.validate_stream_record(rec) is None
    assert {r["facility"] for r in lines} == {"ucb"}


def test_fix_keeps_a_backup(with_all_streams):
    path = paths.stream_lists_dir() / "legacy.jsonl"
    original = '{"geosncl": "HELP.BK.LY_.30", "edid": "01H46MV57FWRWQM3HQBQVTJ1RK"}\n'
    path.write_text(original)
    with pytest.raises(SystemExit):
        _run("validate-streams", "legacy", "--fix")
    assert path.with_suffix(".jsonl.bak").read_text() == original


def test_fix_drops_only_what_it_cannot_resolve(with_all_streams):
    path = paths.stream_lists_dir() / "mixed.jsonl"
    path.write_text(
        json.dumps(GOOD) + "\n"
        + json.dumps({**GOOD, "geosncl": "GHOST.XX.LY_.00"}) + "\n"
        + "not json at all\n")
    with pytest.raises(SystemExit):
        _run("validate-streams", "mixed", "--fix")
    lines = [json.loads(l) for l in path.read_text().splitlines() if l.strip()]
    assert [r["geosncl"] for r in lines] == [GOOD["geosncl"]]


def test_fix_makes_the_list_pass_afterwards(with_all_streams, capsys):
    path = paths.stream_lists_dir() / "legacy.jsonl"
    path.write_text('{"geosncl": "HELP.BK.LY_.30", "edid": "01H46MV57FWRWQM3HQBQVTJ1RK"}\n')
    with pytest.raises(SystemExit):
        _run("validate-streams", "legacy", "--fix")
    capsys.readouterr()
    _run("validate-streams", "legacy")          # must not raise now
    assert "All 1 list(s) valid" in capsys.readouterr().out


def test_fix_deduplicates(with_all_streams):
    path = paths.stream_lists_dir() / "dupes.jsonl"
    path.write_text((json.dumps(GOOD) + "\n") * 3)
    with pytest.raises(SystemExit):
        _run("validate-streams", "dupes", "--fix")
    assert len([l for l in path.read_text().splitlines() if l.strip()]) == 1

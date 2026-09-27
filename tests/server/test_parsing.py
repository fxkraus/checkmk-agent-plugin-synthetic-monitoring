import json

from cmk_addons.plugins.synmon.lib import parsing


def _row(obj):
    # sep(0): each section row is a single cell containing the whole JSON object.
    return [json.dumps(obj)]


def test_parse_journey_section_returns_dicts():
    rows = [
        _row({"journey_name": "login", "status": 0}),
        _row({"journey_name": "search", "status": 2}),
    ]
    result = parsing.parse_journey_section(rows)
    assert [j["journey_name"] for j in result] == ["login", "search"]


def test_parse_journey_section_skips_unparseable_and_keyless():
    rows = [
        _row({"journey_name": "ok", "status": 0}),
        ["{not json"],
        _row({"status": 0}),  # missing journey_name
        _row(["not a dict"]),
        [],  # empty row
    ]
    result = parsing.parse_journey_section(rows)
    assert [j["journey_name"] for j in result] == ["ok"]


def test_parse_worker_section_returns_first_dict_or_none():
    assert (
        parsing.parse_worker_section([_row({"worker_id": "w1", "heartbeat_at": 1.0})])["worker_id"]
        == "w1"
    )
    assert parsing.parse_worker_section([]) is None
    assert parsing.parse_worker_section([["{bad"]]) is None

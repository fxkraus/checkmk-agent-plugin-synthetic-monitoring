"""Parse synmon agent sections (sep(0): one JSON object per row). Standard library only."""

from __future__ import annotations

import json


def _loads_rows(string_table: list[list[str]]) -> list[dict]:
    out: list[dict] = []
    for row in string_table:
        if not row:
            continue
        try:
            obj = json.loads(row[0])
        except (ValueError, IndexError):
            continue
        if isinstance(obj, dict):
            out.append(obj)
    return out


def parse_journey_section(string_table: list[list[str]]) -> list[dict]:
    return [obj for obj in _loads_rows(string_table) if "journey_name" in obj]


def parse_worker_section(string_table: list[list[str]]) -> dict | None:
    rows = _loads_rows(string_table)
    return rows[0] if rows else None

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


def _started(journey: dict) -> float:
    value = journey.get("started_at")
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else 0.0


def index_journeys(journeys: list[dict]) -> dict[str, dict]:
    """Key journeys by name. Piggyback data from several workers can repeat a name: keep the
    newest result and list the reporting workers under ``duplicate_workers``."""
    by_name: dict[str, list[dict]] = {}
    for journey in journeys:
        by_name.setdefault(str(journey["journey_name"]), []).append(journey)
    out: dict[str, dict] = {}
    for name, entries in by_name.items():
        newest = max(entries, key=_started)
        if len(entries) > 1:
            workers = sorted({str(e.get("worker_id")) for e in entries})
            newest = {**newest, "duplicate_workers": workers}
        out[name] = newest
    return out


def parse_worker_section(string_table: list[list[str]]) -> dict | None:
    rows = _loads_rows(string_table)
    return rows[0] if rows else None

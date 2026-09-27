#!/usr/bin/env python3
"""Checkmk agent plugin: read the synthetic-monitoring spool, emit agent sections.

Standard library only. Never launches a browser; tolerates missing/partial/corrupt files.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

SCHEMA_VERSION = "1.0.0"
SPOOL_DIR = Path(os.environ.get("SYNMON_SPOOL_DIR", "/var/lib/synmon/spool"))
HEARTBEAT_PATH = Path(os.environ.get("SYNMON_HEARTBEAT_PATH", "/var/lib/synmon/heartbeat.json"))

_HEARTBEAT_KEYS = (
    "worker_id",
    "executor",
    "executor_version",
    "heartbeat_at",
    "last_run_started_at",
    "last_run_finished_at",
    "last_run_duration_ms",
    "journeys_run",
    "journeys_failed",
    "journeys_skipped",
    "load_errors",
)


def _load_results(spool_dir: Path):
    results = []
    unparseable = 0
    if not spool_dir.is_dir():
        return results, unparseable
    for path in sorted(spool_dir.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            unparseable += 1
            continue
        if not isinstance(data, dict) or "target_host" not in data or "journey_name" not in data:
            unparseable += 1
            continue
        results.append(data)
    return results, unparseable


def _load_heartbeat(path: Path):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _emit_worker(heartbeat, results, unparseable, out) -> None:
    payload = {
        "schema_version": SCHEMA_VERSION,
        "results_found": len(results),
        "unparseable": unparseable,
    }
    if heartbeat is not None:
        for key in _HEARTBEAT_KEYS:
            if key in heartbeat:
                payload[key] = heartbeat[key]
    out.write("<<<synmon_worker:sep(0)>>>\n")
    out.write(json.dumps(payload, sort_keys=True) + "\n")


def _emit_journeys(results, out) -> None:
    by_host: dict[str, list[dict]] = {}
    for result in results:
        by_host.setdefault(result["target_host"], []).append(result)
    for host in sorted(by_host):
        out.write(f"<<<<{host}>>>>\n")
        out.write("<<<synmon_journey:sep(0)>>>\n")
        for result in by_host[host]:
            out.write(json.dumps(result, sort_keys=True) + "\n")
        out.write("<<<<>>>>\n")


def main(
    spool_dir: Path = SPOOL_DIR,
    heartbeat_path: Path = HEARTBEAT_PATH,
    out=sys.stdout,
) -> None:
    results, unparseable = _load_results(spool_dir)
    heartbeat = _load_heartbeat(heartbeat_path)
    _emit_worker(heartbeat, results, unparseable, out)
    _emit_journeys(results, out)


if __name__ == "__main__":
    main()

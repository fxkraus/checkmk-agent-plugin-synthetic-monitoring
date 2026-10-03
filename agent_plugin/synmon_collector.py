#!/usr/bin/env python3
"""Checkmk agent plugin: read the synthetic-monitoring spool, emit agent sections.

Standard library only. Never launches a browser; tolerates missing/partial/corrupt files.
"""

from __future__ import annotations

import json
import os
import re
import stat
import sys
from pathlib import Path

SCHEMA_VERSION = "1.0.0"
SPOOL_DIR = Path(os.environ.get("SYNMON_SPOOL_DIR", "/var/lib/synmon/spool"))
HEARTBEAT_PATH = Path(os.environ.get("SYNMON_HEARTBEAT_PATH", "/var/lib/synmon/heartbeat.json"))
MAX_FILE_BYTES = 1024 * 1024
# Must match the contract's target_host pattern; anything else could forge piggyback headers.
_HOST_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,252}")

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
    "run_error",
)


def _read_json(path: Path):
    """Read a regular file, never following symlinks or blocking on FIFOs (the agent runs as
    root over a directory an unprivileged user can write). Raises OSError/ValueError."""
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as fh:
        info = os.fstat(fh.fileno())
        if not stat.S_ISREG(info.st_mode):
            raise ValueError("not a regular file")
        data = fh.read(MAX_FILE_BYTES + 1)
    if len(data) > MAX_FILE_BYTES:
        raise ValueError("file too large")
    return json.loads(data.decode("utf-8"))


def _is_valid_result(data) -> bool:
    return (
        isinstance(data, dict)
        and isinstance(data.get("target_host"), str)
        and _HOST_RE.fullmatch(data["target_host"]) is not None
        and isinstance(data.get("journey_name"), str)
    )


def _load_results(spool_dir: Path):
    results = []
    unparseable = 0
    if not spool_dir.is_dir():
        return results, unparseable
    for path in sorted(spool_dir.glob("*.json")):
        try:
            data = _read_json(path)
        except (OSError, ValueError):
            unparseable += 1
            continue
        if not _is_valid_result(data):
            unparseable += 1
            continue
        results.append(data)
    return results, unparseable


def _load_heartbeat(path: Path):
    try:
        data = _read_json(path)
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

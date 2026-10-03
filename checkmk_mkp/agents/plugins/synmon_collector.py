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
# Root-owned, one host per line: the only target hosts this worker may send piggyback data to.
ALLOWED_HOSTS_PATH = Path(os.environ.get("SYNMON_ALLOWED_HOSTS", "/etc/synmon/allowed_hosts"))
MAX_FILE_BYTES = 1024 * 1024
# Bound what a compromised executor can make the root agent read and print.
MAX_FILES = 500
MAX_TOTAL_BYTES = 16 * 1024 * 1024
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


def _read_bytes(path, dir_fd=None) -> bytes:
    """Read a regular file, never following symlinks or blocking on FIFOs (the agent runs as
    root over a directory an unprivileged user can write). Raises OSError/ValueError."""
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=dir_fd)
    with os.fdopen(fd, "rb") as fh:
        info = os.fstat(fh.fileno())
        if not stat.S_ISREG(info.st_mode):
            raise ValueError("not a regular file")
        data = fh.read(MAX_FILE_BYTES + 1)
    if len(data) > MAX_FILE_BYTES:
        raise ValueError("file too large")
    return data


def _read_json(path, dir_fd=None):
    return json.loads(_read_bytes(path, dir_fd).decode("utf-8"))


def _load_allowed_hosts(path: Path):
    """The allowlist as a set, or None if there is none (then every valid host is accepted)."""
    try:
        text = _read_bytes(path).decode("utf-8")
    except FileNotFoundError:
        return None
    except (OSError, ValueError):
        return set()  # unreadable or tampered with: fail closed
    hosts = set()
    for line in text.splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            hosts.add(line)
    return hosts


def _is_valid_result(data) -> bool:
    return (
        isinstance(data, dict)
        and isinstance(data.get("target_host"), str)
        and _HOST_RE.fullmatch(data["target_host"]) is not None
        and isinstance(data.get("journey_name"), str)
    )


def _load_results(spool_dir: Path, allowed_hosts):
    """Return (results, counts). Opens the spool itself without following a symlink, so a
    replaced spool directory cannot point the root agent at another directory."""
    counts = {"unparseable": 0, "not_allowed": 0, "overflow": 0}
    results = []
    try:
        dir_fd = os.open(spool_dir, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    except FileNotFoundError:
        return results, counts
    except OSError:
        counts["unparseable"] += 1
        return results, counts
    try:
        with os.scandir(dir_fd) as entries:
            names = sorted(e.name for e in entries if e.name.endswith(".json"))
        total = 0
        for index, name in enumerate(names):
            if index >= MAX_FILES or total >= MAX_TOTAL_BYTES:
                counts["overflow"] = len(names) - index
                break
            try:
                raw = _read_bytes(name, dir_fd)
                total += len(raw)
                data = json.loads(raw.decode("utf-8"))
            except (OSError, ValueError):
                counts["unparseable"] += 1
                continue
            if not _is_valid_result(data):
                counts["unparseable"] += 1
            elif allowed_hosts is not None and data["target_host"] not in allowed_hosts:
                counts["not_allowed"] += 1
            else:
                results.append(data)
    finally:
        os.close(dir_fd)
    return results, counts


def _load_heartbeat(path: Path):
    try:
        data = _read_json(path)
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _emit_worker(heartbeat, results, counts, allowlist: bool, out) -> None:
    payload = {
        "schema_version": SCHEMA_VERSION,
        "results_found": len(results),
        "allowlist": allowlist,
        **counts,
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
    allowed_hosts_path: Path = ALLOWED_HOSTS_PATH,
) -> None:
    allowed_hosts = _load_allowed_hosts(allowed_hosts_path)
    results, counts = _load_results(spool_dir, allowed_hosts)
    heartbeat = _load_heartbeat(heartbeat_path)
    _emit_worker(heartbeat, results, counts, allowed_hosts is not None, out)
    _emit_journeys(results, out)


if __name__ == "__main__":
    main()

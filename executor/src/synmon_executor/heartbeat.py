"""Atomic heartbeat writer."""

from __future__ import annotations

import os
from pathlib import Path

from synmon_contract.models import Heartbeat


def write_heartbeat_atomic(hb: Heartbeat, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Deterministic "<name>.tmp" is safe under the single-writer design (journeys run
    # sequentially; systemd serializes executor runs). If a spool dir is ever shared by
    # concurrent writers, replace with a unique suffix (e.g. uuid4) to avoid collisions.
    tmp = path.with_name(path.name + ".tmp")
    data = hb.model_dump_json().encode("utf-8")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o640)
    try:
        os.write(fd, data)
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(tmp, path)
    return path

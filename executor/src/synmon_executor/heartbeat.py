"""Atomic heartbeat writer."""

from __future__ import annotations

from pathlib import Path

from synmon_contract.models import Heartbeat

from synmon_executor.atomic import write_atomic


def write_heartbeat_atomic(hb: Heartbeat, path: Path) -> Path:
    return write_atomic(path, hb.model_dump_json().encode("utf-8"))

"""Atomic spool writer: temp file -> fsync -> rename."""

from __future__ import annotations

import os
import re
from collections.abc import Iterable
from pathlib import Path

from synmon_contract.models import JourneyResult


def _safe(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value)


def result_stem(target_host: str, journey_id: str) -> str:
    """File stem shared by a journey's spool result and its artifacts.

    Not injective on its own; discovery rejects journeys whose stems collide.
    """
    return f"{_safe(target_host)}__{_safe(journey_id)}"


def result_filename(target_host: str, journey_id: str) -> str:
    return f"{result_stem(target_host, journey_id)}.json"


def write_result_atomic(result: JourneyResult, spool_dir: Path) -> Path:
    spool_dir.mkdir(parents=True, exist_ok=True)
    final = spool_dir / result_filename(result.target_host, result.journey_id)
    # Deterministic "<name>.tmp" is safe under the single-writer design (journeys run
    # sequentially; systemd serializes executor runs). If a spool dir is ever shared by
    # concurrent writers, replace with a unique suffix (e.g. uuid4) to avoid collisions.
    tmp = final.with_name(final.name + ".tmp")
    data = result.model_dump_json().encode("utf-8")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o640)
    try:
        os.write(fd, data)
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(tmp, final)
    return final


def prune_spool(spool_dir: Path, keep: Iterable[str]) -> int:
    """Remove results of journeys that no longer exist, so their services do not stay stale."""
    if not spool_dir.is_dir():
        return 0
    keep = set(keep)
    removed = 0
    for entry in spool_dir.glob("*.json"):
        if entry.name not in keep and (entry.is_symlink() or not entry.is_dir()):
            entry.unlink()
            removed += 1
    return removed

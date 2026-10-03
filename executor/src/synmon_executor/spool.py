"""Atomic spool writer: temp file -> fsync -> rename."""

from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path

from synmon_contract.models import JourneyResult

from synmon_executor.atomic import write_atomic


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
    final = spool_dir / result_filename(result.target_host, result.journey_id)
    return write_atomic(final, result.model_dump_json().encode("utf-8"))


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

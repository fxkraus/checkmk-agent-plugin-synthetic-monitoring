"""On-disk artifact retention (bounds the spool's sibling artifacts dir)."""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path


def prune_artifacts(
    artifacts_dir: Path,
    max_age_s: int,
    now: Callable[[], float] = time.time,
) -> int:
    if not artifacts_dir.is_dir():
        return 0
    cutoff = now() - max_age_s
    removed = 0
    for entry in artifacts_dir.iterdir():
        if entry.is_file() and entry.stat().st_mtime < cutoff:
            entry.unlink()
            removed += 1
    return removed

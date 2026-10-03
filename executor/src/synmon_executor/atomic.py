"""Atomic file replacement: temp file -> full write -> fsync -> rename -> fsync dir."""

from __future__ import annotations

import os
from pathlib import Path


def write_atomic(path: Path, data: bytes, mode: int = 0o640) -> Path:
    """Replace ``path`` with ``data`` so readers see the old or the new content, never a mix.

    The deterministic "<name>.tmp" is safe under the single-writer design (journeys run
    sequentially; systemd serializes executor runs). If a directory is ever shared by concurrent
    writers, replace it with a unique suffix (e.g. uuid4) to avoid collisions.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode)
    try:
        view = memoryview(data)
        while view:
            view = view[os.write(fd, view) :]
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(tmp, path)
    dir_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(dir_fd)
    finally:
        os.close(dir_fd)
    return path

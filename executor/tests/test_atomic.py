import os

import pytest
from synmon_executor import atomic


def test_short_writes_are_completed(tmp_path, monkeypatch):
    real_write = os.write

    def one_byte_at_a_time(fd, data):
        return real_write(fd, bytes(data[:1]))

    monkeypatch.setattr(atomic.os, "write", one_byte_at_a_time)
    path = atomic.write_atomic(tmp_path / "r.json", b'{"ok": true}')
    assert path.read_bytes() == b'{"ok": true}'


def test_failed_write_keeps_the_previous_file(tmp_path, monkeypatch):
    path = atomic.write_atomic(tmp_path / "r.json", b"old")

    def no_space(fd, data):  # noqa: ARG001
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(atomic.os, "write", no_space)
    with pytest.raises(OSError):
        atomic.write_atomic(path, b"new")
    assert path.read_bytes() == b"old"


def test_file_mode_is_group_readable_only(tmp_path):
    old = os.umask(0)
    try:
        path = atomic.write_atomic(tmp_path / "r.json", b"x")
    finally:
        os.umask(old)
    assert path.stat().st_mode & 0o777 == 0o640

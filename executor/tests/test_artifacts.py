import os

from synmon_executor.artifacts import prune_artifacts


def test_prune_removes_old_keeps_new(tmp_path):
    old = tmp_path / "old.png"
    new = tmp_path / "new.png"
    old.write_bytes(b"x")
    new.write_bytes(b"y")
    os.utime(old, (1000.0, 1000.0))
    os.utime(new, (9000.0, 9000.0))

    removed = prune_artifacts(tmp_path, max_age_s=100, now=lambda: 9000.0)

    assert removed == 1
    assert not old.exists()
    assert new.exists()


def test_prune_missing_dir_is_noop(tmp_path):
    assert prune_artifacts(tmp_path / "nope", max_age_s=10, now=lambda: 0.0) == 0

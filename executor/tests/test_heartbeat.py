import json

from synmon_contract.models import Heartbeat
from synmon_executor.heartbeat import write_heartbeat_atomic


def _hb() -> Heartbeat:
    return Heartbeat(
        schema_version="1.0.0",
        worker_id="w1",
        executor="playwright",
        executor_version="1.49.0",
        heartbeat_at=1000.0,
        journeys_run=2,
        journeys_failed=0,
    )


def test_heartbeat_written_atomically(tmp_path):
    path = tmp_path / "sub" / "heartbeat.json"
    write_heartbeat_atomic(_hb(), path)
    assert path.exists()
    assert json.loads(path.read_text("utf-8"))["worker_id"] == "w1"
    assert list(path.parent.glob("*.tmp")) == []

import json

from synmon_contract.models import JourneyResult
from synmon_executor.spool import result_filename, write_result_atomic


def _result(**over) -> JourneyResult:
    base = dict(
        executor="playwright",
        executor_version="1.49.0",
        worker_id="w1",
        target_host="app.example.com",
        journey_name="login",
        journey_id="login",
        status=0,
        summary="ok",
        started_at=1000.0,
        duration_ms=5,
        max_age_s=900,
        interval_s=300,
    )
    base.update(over)
    return JourneyResult(**base)


def test_result_filename_is_safe():
    assert result_filename("app.example.com", "login") == "app.example.com__login.json"
    assert "/" not in result_filename("a/b", "c d")


def test_write_creates_file_and_no_tmp_left(tmp_path):
    path = write_result_atomic(_result(), tmp_path)
    assert path.exists()
    assert json.loads(path.read_text("utf-8"))["journey_name"] == "login"
    assert list(tmp_path.glob("*.tmp")) == []


def test_write_is_idempotent_overwrite(tmp_path):
    write_result_atomic(_result(summary="first"), tmp_path)
    path = write_result_atomic(_result(summary="second"), tmp_path)
    assert json.loads(path.read_text("utf-8"))["summary"] == "second"
    assert len(list(tmp_path.glob("*.json"))) == 1

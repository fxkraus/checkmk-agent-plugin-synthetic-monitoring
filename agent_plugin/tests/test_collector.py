import importlib.util
import io
import json
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1] / "synmon_collector.py"


def _load():
    spec = importlib.util.spec_from_file_location("synmon_collector", PLUGIN)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _result(target, journey_id, **over):
    base = {
        "schema_version": "1.0.0",
        "executor": "playwright",
        "executor_version": "1.49.0",
        "worker_id": "w1",
        "target_host": target,
        "journey_name": journey_id,
        "journey_id": journey_id,
        "status": 0,
        "summary": "ok",
        "started_at": 1000.0,
        "duration_ms": 5,
        "max_age_s": 900,
        "interval_s": 300,
        "steps": [],
        "artifacts": {"screenshot_path": None, "trace_path": None},
        "error": None,
        "labels": {},
    }
    base.update(over)
    return base


def test_emits_worker_and_piggyback_sections(tmp_path):
    mod = _load()
    spool = tmp_path / "spool"
    spool.mkdir()
    (spool / "a__one.json").write_text(json.dumps(_result("a.example.com", "one")), "utf-8")
    (spool / "a__two.json").write_text(json.dumps(_result("a.example.com", "two")), "utf-8")
    (spool / "b__three.json").write_text(json.dumps(_result("b.example.com", "three")), "utf-8")
    (spool / "broken.json").write_text("{not json", "utf-8")
    hb = tmp_path / "heartbeat.json"
    hb.write_text(
        json.dumps(
            {
                "worker_id": "w1",
                "executor": "playwright",
                "heartbeat_at": 1000.0,
                "journeys_run": 3,
                "journeys_failed": 0,
            }
        ),
        "utf-8",
    )

    buf = io.StringIO()
    mod.main(spool_dir=spool, heartbeat_path=hb, out=buf)
    output = buf.getvalue()
    lines = output.splitlines()

    # Worker section first, with counts.
    assert lines[0] == "<<<synmon_worker:sep(0)>>>"
    worker = json.loads(lines[1])
    assert worker["results_found"] == 3 and worker["unparseable"] == 1
    assert worker["worker_id"] == "w1"

    # Piggyback blocks in sorted host order, journeys grouped per host.
    assert "<<<<a.example.com>>>>" in lines
    assert "<<<<b.example.com>>>>" in lines
    assert output.count("<<<synmon_journey:sep(0)>>>") == 2
    assert "<<<<>>>>" in lines
    a_idx = lines.index("<<<<a.example.com>>>>")
    assert lines[a_idx + 1] == "<<<synmon_journey:sep(0)>>>"
    assert json.loads(lines[a_idx + 2])["target_host"] == "a.example.com"

    # Assert sorted host order: a comes before b.
    assert lines.index("<<<<a.example.com>>>>") < lines.index("<<<<b.example.com>>>>")

    # Assert sorted journey order within host a: one before two.
    journey_one = json.loads(lines[a_idx + 2])
    journey_two = json.loads(lines[a_idx + 3])
    assert journey_one["journey_name"] == "one"
    assert journey_two["journey_name"] == "two"


def test_missing_spool_and_heartbeat_is_graceful(tmp_path):
    mod = _load()
    buf = io.StringIO()
    mod.main(spool_dir=tmp_path / "nope", heartbeat_path=tmp_path / "nohb.json", out=buf)
    lines = buf.getvalue().splitlines()
    assert lines[0] == "<<<synmon_worker:sep(0)>>>"
    worker = json.loads(lines[1])
    assert worker["results_found"] == 0 and worker["unparseable"] == 0
    # No piggyback sections when there are no results.
    assert "<<<synmon_journey:sep(0)>>>" not in buf.getvalue()


def test_passes_through_load_errors_and_skips(tmp_path):
    mod = _load()
    hb = tmp_path / "heartbeat.json"
    hb.write_text(
        json.dumps(
            {
                "heartbeat_at": 1000.0,
                "load_errors": ["x.py: SyntaxError: bad"],
                "journeys_skipped": 1,
            }
        ),
        "utf-8",
    )
    buf = io.StringIO()
    mod.main(spool_dir=tmp_path / "nope", heartbeat_path=hb, out=buf)
    worker = json.loads(buf.getvalue().splitlines()[1])
    assert worker["load_errors"] == ["x.py: SyntaxError: bad"]
    assert worker["journeys_skipped"] == 1

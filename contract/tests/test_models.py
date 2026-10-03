import json

from synmon_contract.models import (
    SCHEMA_VERSION,
    Artifacts,
    Heartbeat,
    JourneyError,
    JourneyResult,
    Status,
    Step,
    Vitals,
    WorkerHealth,
)


def _minimal_result(**over) -> JourneyResult:
    base = dict(
        executor="playwright",
        executor_version="1.49.0",
        worker_id="worker-1",
        target_host="app.example.com",
        journey_name="login",
        journey_id="login",
        status=0,
        summary="ok",
        started_at=1000.0,
        duration_ms=1234,
        max_age_s=900,
        interval_s=300,
    )
    base.update(over)
    return JourneyResult(**base)


def test_status_enum_values():
    assert (Status.OK, Status.WARN, Status.CRIT, Status.UNKNOWN) == (0, 1, 2, 3)


def test_minimal_result_defaults():
    r = _minimal_result()
    assert r.schema_version == SCHEMA_VERSION == "1.0.0"
    assert r.steps == []
    assert r.artifacts == Artifacts()
    assert r.error is None
    assert r.labels == {}


def test_result_roundtrips_through_json():
    r = _minimal_result(
        steps=[Step(name="open", status=0, duration_ms=10, started_at=1000.0)],
        artifacts=Artifacts(screenshot_path="/a/s.png", trace_path="/a/t.zip"),
        error=JourneyError(type="TimeoutError", message="boom", step="open"),
        labels={"env": "prod"},
    )
    blob = r.model_dump_json()
    again = JourneyResult.model_validate_json(blob)
    assert again == r
    assert "\n" not in blob  # one-line section row


def test_status_bounds_validated():
    import pytest

    with pytest.raises(ValueError):
        _minimal_result(status=4)


def test_unknown_fields_ignored_for_forward_compat():
    data = json.loads(_minimal_result().model_dump_json())
    data["future"] = 1
    r = JourneyResult.model_validate(data)
    assert r.journey_name == "login"


def test_worker_health_minimal():
    w = WorkerHealth(schema_version=SCHEMA_VERSION, results_found=2, unparseable=1)
    assert w.worker_id is None and w.results_found == 2


def test_heartbeat_roundtrip():
    hb = Heartbeat(
        schema_version=SCHEMA_VERSION,
        worker_id="worker-1",
        executor="playwright",
        executor_version="1.49.0",
        heartbeat_at=1000.0,
        journeys_run=3,
        journeys_failed=1,
    )
    assert Heartbeat.model_validate_json(hb.model_dump_json()) == hb


def test_vitals_optional_and_ignores_extra():
    v = Vitals(lcp_ms=1234.5, cls=0.05)
    assert v.lcp_ms == 1234.5 and v.cls == 0.05
    assert v.inp_ms is None
    # forward-compat: unknown keys ignored
    v2 = Vitals.model_validate({"lcp_ms": 1.0, "future_metric": 9})
    assert v2.lcp_ms == 1.0


def test_step_and_result_accept_vitals():
    step = Step(name="open", status=0, duration_ms=500, vitals=Vitals(lcp_ms=900.0))
    assert step.vitals.lcp_ms == 900.0
    jr = JourneyResult(
        executor="playwright",
        executor_version="1.49.0",
        worker_id="w1",
        target_host="h",
        journey_name="j",
        journey_id="j",
        status=0,
        summary="ok",
        started_at=1.0,
        duration_ms=1,
        max_age_s=1,
        interval_s=1,
        vitals=Vitals(lcp_ms=900.0, cls=0.01),
    )
    assert jr.vitals.cls == 0.01
    assert jr.steps == []  # default unchanged


def test_journey_result_attempts_defaults_to_one():
    from synmon_contract.models import JourneyResult

    jr = JourneyResult(
        executor="playwright",
        executor_version="1.49.0",
        worker_id="w1",
        target_host="h",
        journey_name="j",
        journey_id="j",
        status=0,
        summary="ok",
        started_at=1.0,
        duration_ms=1,
        max_age_s=1,
        interval_s=1,
    )
    assert jr.attempts == 1
    jr2 = JourneyResult.model_validate({**jr.model_dump(), "attempts": 3})
    assert jr2.attempts == 3


def test_target_host_rejects_piggyback_header_characters():
    import pytest
    from pydantic import ValidationError

    for bad in ["", "a>>>>", "a\nb", "-lead", "a b", "<<<x>>>", "a/b"]:
        with pytest.raises(ValidationError):
            _minimal_result(target_host=bad)
    assert _minimal_result(target_host="Web_01.example-corp.com").target_host


def test_heartbeat_run_error_defaults_to_none():
    hb = Heartbeat(worker_id="w", executor="playwright", executor_version="1", heartbeat_at=1.0)
    assert hb.run_error is None
    assert WorkerHealth().run_error is None

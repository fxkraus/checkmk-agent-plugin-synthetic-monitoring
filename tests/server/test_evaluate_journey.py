from cmk_addons.plugins.synmon.lib import evaluate
from cmk_addons.plugins.synmon.lib.evaluate import CRIT, OK, UNKNOWN, WARN


def _journey(**over):
    base = {
        "journey_name": "login",
        "status": 0,
        "summary": "login: OK (2 steps)",
        "started_at": 1000.0,
        "duration_ms": 1500,
        "max_age_s": 900,
        "interval_s": 300,
        "steps": [
            {"name": "open", "status": 0, "duration_ms": 500, "message": None},
            {"name": "submit", "status": 0, "duration_ms": 1000, "message": None},
        ],
        "artifacts": {"screenshot_path": None, "trace_path": None},
        "error": None,
    }
    base.update(over)
    return base


def test_level_state():
    assert evaluate.level_state(5.0, None) == OK
    assert evaluate.level_state(5.0, (10.0, 20.0)) == OK
    assert evaluate.level_state(12.0, (10.0, 20.0)) == WARN
    assert evaluate.level_state(25.0, (10.0, 20.0)) == CRIT


def test_norm_levels_accepts_wato_and_plain_shapes():
    assert evaluate.norm_levels(None) is None
    assert evaluate.norm_levels(("no_levels", None)) is None
    assert evaluate.norm_levels(("fixed", (10.0, 20.0))) == (10.0, 20.0)
    assert evaluate.norm_levels((10.0, 20.0)) == (10.0, 20.0)
    # predictive levels -> no static thresholds
    assert evaluate.norm_levels(("cmk_postprocessed", "predictive_levels", {})) is None


def test_ok_journey_fresh():
    out = evaluate.evaluate_journey(_journey(), {}, now=1000.0 + 60)
    assert out.state == OK
    assert "login: OK" in out.summary
    names = {m.name for m in out.metrics}
    assert "synmon_duration" in names and "synmon_age" in names
    assert any(m.name == "synmon_step_1_duration" for m in out.metrics)


def test_executor_crit_is_respected():
    out = evaluate.evaluate_journey(
        _journey(status=2, error={"type": "TimeoutError", "message": "boom", "step": "submit"}),
        {},
        now=1060.0,
    )
    assert out.state == CRIT
    assert any("TimeoutError" in d for d in out.details)


def test_total_duration_threshold_escalates():
    out = evaluate.evaluate_journey(
        _journey(duration_ms=12000), {"total_duration_levels": (10.0, 20.0)}, now=1060.0
    )
    assert out.state == WARN
    out2 = evaluate.evaluate_journey(
        _journey(duration_ms=25000), {"total_duration_levels": (10.0, 20.0)}, now=1060.0
    )
    assert out2.state == CRIT


def test_total_duration_threshold_accepts_wato_fixed_shape():
    # This is the shape the WATO SimpleLevels form spec actually delivers.
    out = evaluate.evaluate_journey(
        _journey(duration_ms=25000),
        {"total_duration_levels": ("fixed", (10.0, 20.0))},
        now=1060.0,
    )
    assert out.state == CRIT
    dur = next(m for m in out.metrics if m.name == "synmon_duration")
    assert dur.levels == (10.0, 20.0)


def test_per_step_threshold_escalates():
    out = evaluate.evaluate_journey(_journey(), {"step_duration_levels": (0.6, 5.0)}, now=1060.0)
    # step 'submit' is 1.0s > 0.6 warn
    assert out.state == WARN
    assert any(s.name == "submit" and s.state == WARN for s in out.steps)


def test_staleness_escalates_with_grace_and_state():
    # age = now - started = 2000; max_age 900 + grace 100 = 1000 -> stale
    out = evaluate.evaluate_journey(
        _journey(), {"staleness_grace_s": 100, "staleness_state": 2}, now=3000.0
    )
    assert out.state == CRIT
    assert any("Stale" in d for d in out.details)
    # within grace -> not stale
    fresh = evaluate.evaluate_journey(
        _journey(), {"staleness_grace_s": 100, "staleness_state": 2}, now=1000.0 + 950
    )
    assert fresh.state == OK


def test_artifacts_surfaced_in_details():
    out = evaluate.evaluate_journey(
        _journey(status=2, artifacts={"screenshot_path": "/a/x.png", "trace_path": "/a/x.zip"}),
        {},
        now=1060.0,
    )
    assert any("/a/x.png" in d for d in out.details)
    assert any("/a/x.zip" in d for d in out.details)


def test_vitals_metrics_emitted_and_thresholds_escalate():
    j = _journey(
        vitals={"lcp_ms": 3000.0, "cls": 0.2, "inp_ms": 150.0, "fcp_ms": 800.0, "ttfb_ms": 200.0}
    )
    out = evaluate.evaluate_journey(j, {}, now=1060.0)
    names = {m.name for m in out.metrics}
    assert {"synmon_lcp", "synmon_cls", "synmon_inp", "synmon_fcp", "synmon_ttfb"} <= names
    lcp = next(m for m in out.metrics if m.name == "synmon_lcp")
    assert lcp.value == 3.0  # ms -> seconds

    # LCP 3.0s breaches warn 2.5s; CLS 0.2 breaches warn 0.1
    out2 = evaluate.evaluate_journey(
        j, {"lcp_levels": ("fixed", (2.5, 4.0)), "cls_levels": ("fixed", (0.1, 0.25))}, now=1060.0
    )
    assert out2.state == WARN


def test_no_vitals_emits_no_vitals_metrics():
    out = evaluate.evaluate_journey(_journey(), {}, now=1060.0)
    assert not any(m.name.startswith("synmon_lcp") for m in out.metrics)


def test_attempts_metric_and_detail():
    out = evaluate.evaluate_journey(_journey(attempts=3), {}, now=1060.0)
    m = next((m for m in out.metrics if m.name == "synmon_attempts"), None)
    assert m is not None and m.value == 3.0
    assert any("Attempts: 3" in d for d in out.details)

    out1 = evaluate.evaluate_journey(_journey(attempts=1), {}, now=1060.0)
    assert any(m.name == "synmon_attempts" for m in out1.metrics)
    assert not any("Attempts" in d for d in out1.details)  # no detail when not retried


def test_success_only_after_retry_warns_by_default():
    out = evaluate.evaluate_journey(_journey(attempts=2), {}, now=1060.0)
    assert out.state == WARN
    assert "succeeded only after 2 attempts" in out.summary


def test_success_after_retry_state_is_configurable():
    out = evaluate.evaluate_journey(_journey(attempts=2), {"retried_state": OK}, now=1060.0)
    assert out.state == OK


def test_retry_state_never_lowers_a_failure():
    out = evaluate.evaluate_journey(
        _journey(attempts=3, status=CRIT), {"retried_state": OK}, now=1060.0
    )
    assert out.state == CRIT


def test_stale_result_is_unknown_by_default():
    out = evaluate.evaluate_journey(_journey(), {}, now=3000.0)
    assert out.state == UNKNOWN


def test_stale_state_replaces_the_outdated_result_state():
    # An old CRIT says nothing about the application now; SLA reporting should see "unknown".
    out = evaluate.evaluate_journey(_journey(status=CRIT), {}, now=3000.0)
    assert out.state == UNKNOWN
    assert out.summary.startswith("Stale result")

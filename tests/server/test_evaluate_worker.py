from cmk_addons.plugins.synmon.lib import evaluate
from cmk_addons.plugins.synmon.lib.evaluate import CRIT, OK, UNKNOWN, WARN


def _worker(**over):
    base = {
        "worker_id": "w1",
        "executor": "playwright",
        "heartbeat_at": 1000.0,
        "journeys_run": 3,
        "journeys_failed": 0,
        "results_found": 3,
        "unparseable": 0,
    }
    base.update(over)
    return base


def test_fresh_worker_ok():
    out = evaluate.evaluate_worker(_worker(), {"heartbeat_age_levels": (300.0, 600.0)}, now=1100.0)
    assert out.state == OK
    assert "3 result" in out.summary
    assert any(m.name == "synmon_heartbeat_age" for m in out.metrics)


def test_missing_heartbeat_is_unknown():
    out = evaluate.evaluate_worker(_worker(heartbeat_at=None), {}, now=1100.0)
    assert out.state == UNKNOWN
    assert "heartbeat" in out.summary.lower()


def test_heartbeat_age_levels_escalate():
    out = evaluate.evaluate_worker(
        _worker(), {"heartbeat_age_levels": (300.0, 600.0)}, now=1000.0 + 700
    )
    assert out.state == CRIT


def test_heartbeat_age_levels_accept_wato_fixed_shape():
    out = evaluate.evaluate_worker(
        _worker(), {"heartbeat_age_levels": ("fixed", (300.0, 600.0))}, now=1000.0 + 700
    )
    assert out.state == CRIT


def test_unparseable_files_warn():
    out = evaluate.evaluate_worker(_worker(unparseable=2), {}, now=1100.0)
    assert out.state == WARN
    assert any("unparseable" in d for d in out.details)


def test_journey_load_errors_warn_and_are_listed():
    out = evaluate.evaluate_worker(_worker(load_errors=["x.py: SyntaxError: bad"]), {}, now=1100.0)
    assert out.state == WARN
    assert "1 journey file(s) failed to load" in out.summary
    assert "x.py: SyntaxError: bad" in out.details


def test_skipped_journeys_warn():
    out = evaluate.evaluate_worker(_worker(journeys_skipped=2), {}, now=1100.0)
    assert out.state == WARN
    assert "2 skipped (run budget exhausted)" in out.summary
    assert any(m.name == "synmon_journeys_skipped" and m.value == 2 for m in out.metrics)


def test_run_error_is_crit_and_explained():
    out = evaluate.evaluate_worker(_worker(run_error="Error: no browser"), {}, now=1100.0)
    assert out.state == CRIT
    assert "last run failed: Error: no browser" in out.summary


def test_non_list_load_errors_are_ignored():
    out = evaluate.evaluate_worker(_worker(load_errors="oops"), {}, now=1100.0)
    assert out.state == OK


def test_dropped_hosts_and_overflow_warn():
    out = evaluate.evaluate_worker(_worker(not_allowed=2, allowlist=True), {}, now=1000.0)
    assert out.state == WARN and "2 result(s) for hosts not in the allowlist" in out.summary
    out = evaluate.evaluate_worker(_worker(overflow=7, allowlist=True), {}, now=1000.0)
    assert out.state == WARN and "7 spool file(s) not read" in out.summary


def test_missing_allowlist_warns_but_an_old_plugin_does_not():
    out = evaluate.evaluate_worker(_worker(allowlist=False), {}, now=1000.0)
    assert out.state == WARN and "no target-host allowlist" in out.summary
    assert evaluate.evaluate_worker(_worker(), {}, now=1000.0).state == OK

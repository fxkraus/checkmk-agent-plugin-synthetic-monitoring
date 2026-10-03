import asyncio

from synmon_executor.sdk import (
    StepRecorder,
    clear_registry,
    journey,
    registered_journeys,
    slugify,
)


def test_slugify():
    assert slugify("Login Flow!") == "login-flow"
    assert slugify("") == "journey"


def test_journey_registers():
    clear_registry()

    @journey(name="Login Flow", target_host="app.example.com", max_age_s=900, interval_s=300)
    async def _run(page, ctx):  # noqa: ARG001
        return None

    (jd,) = registered_journeys()
    assert jd.name == "Login Flow"
    assert jd.journey_id == "login-flow"
    assert jd.target_host == "app.example.com"
    assert jd.max_age_s == 900 and jd.interval_s == 300


def test_step_recorder_success():
    rec = StepRecorder(wall=lambda: 1000.0, mono=_fake_mono([0.0, 0.05]))

    async def go():
        async with rec.step("open"):
            pass

    asyncio.run(go())
    assert len(rec.steps) == 1
    s = rec.steps[0]
    assert s.name == "open" and s.status == 0 and s.duration_ms == 50
    assert s.started_at == 1000.0 and s.message is None
    assert rec.last_failed_step is None


def test_step_recorder_failure_records_and_reraises():
    rec = StepRecorder(wall=lambda: 1000.0, mono=_fake_mono([0.0, 0.10]))

    async def go():
        async with rec.step("submit"):
            raise RuntimeError("nope")

    try:
        asyncio.run(go())
        raise AssertionError("expected RuntimeError")
    except RuntimeError:
        pass
    s = rec.steps[0]
    assert s.status == 2 and s.duration_ms == 100
    assert "RuntimeError: nope" in s.message
    assert rec.last_failed_step == "submit"


def _fake_mono(values):
    it = iter(values)
    return lambda: next(it)


def test_journey_retries_timeout_defaults_none():
    from synmon_executor import sdk

    sdk.clear_registry()

    @sdk.journey(name="j", target_host="h", max_age_s=1, interval_s=1, retries=2, timeout_s=30.0)
    async def _j(page, ctx):
        pass

    jd = sdk.registered_journeys()[0]
    assert jd.retries == 2 and jd.timeout_s == 30.0


def test_login_registers_and_clear_resets_both():
    from synmon_executor import sdk

    sdk.clear_registry()

    @sdk.login(target_host="app", name="signin", max_age_s=1, interval_s=1)
    async def _l(page, ctx):
        pass

    logins = sdk.registered_logins()
    assert len(logins) == 1
    assert logins[0].target_host == "app" and logins[0].name == "signin"
    assert logins[0].login_id == "signin"
    sdk.clear_registry()
    assert sdk.registered_logins() == [] and sdk.registered_journeys() == []


def test_decorators_reject_invalid_arguments():
    import pytest
    from synmon_executor.sdk import journey, login

    bad = [
        {"retries": -1},
        {"timeout_s": 0},
        {"max_age_s": -5},
        {"interval_s": -1},
    ]
    for over in bad:
        args = {"name": "x", "target_host": "h", "max_age_s": 60, "interval_s": 60, **over}
        with pytest.raises(ValueError):
            journey(**args)
        with pytest.raises(ValueError):
            login(**args)

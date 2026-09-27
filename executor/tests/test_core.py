import asyncio
import time
from contextlib import asynccontextmanager

from synmon_contract.models import Artifacts, JourneyResult
from synmon_executor.core import run_journey, run_journey_resilient, run_login
from synmon_executor.sdk import JourneyDef, LoginDef


class FakeSession:
    def __init__(self) -> None:
        self.page = object()
        self.captured: list[str] = []

    async def capture_failure(self, journey_id: str) -> Artifacts:
        self.captured.append(journey_id)
        return Artifacts(screenshot_path=f"/a/{journey_id}.png", trace_path=f"/a/{journey_id}.zip")


def _jd(func) -> JourneyDef:
    return JourneyDef(
        name="login",
        journey_id="login",
        target_host="app.example.com",
        max_age_s=900,
        interval_s=300,
        func=func,
        labels={"env": "prod"},
    )


def test_successful_journey_builds_ok_result():
    async def run(page, ctx):  # noqa: ARG001
        async with ctx.step("open"):
            pass
        async with ctx.step("submit"):
            pass

    session = FakeSession()
    result = asyncio.run(
        run_journey(
            _jd(run), session, worker_id="w1", executor="playwright", executor_version="1.49.0"
        )
    )
    assert isinstance(result, JourneyResult)
    assert result.status == 0
    assert [s.name for s in result.steps] == ["open", "submit"]
    assert result.error is None
    assert result.artifacts == Artifacts()
    assert session.captured == []
    assert result.target_host == "app.example.com" and result.labels == {"env": "prod"}


def test_failed_journey_captures_artifacts_and_marks_crit():
    async def run(page, ctx):  # noqa: ARG001
        async with ctx.step("open"):
            pass
        async with ctx.step("submit"):
            raise TimeoutError("locator not found")

    session = FakeSession()
    result = asyncio.run(
        run_journey(
            _jd(run), session, worker_id="w1", executor="playwright", executor_version="1.49.0"
        )
    )
    assert result.status == 2
    assert result.error is not None
    assert result.error.type == "TimeoutError"
    assert result.error.step == "submit"
    assert result.artifacts.screenshot_path == "/a/login.png"
    assert session.captured == ["login"]
    # The failing step is recorded CRIT, the prior step OK.
    assert [s.status for s in result.steps] == [0, 2]


class _Fake:
    page = object()

    def __init__(self, state=None):
        self._state = state if state is not None else {"cookies": []}
        self.seen_state = "unset"

    async def capture_failure(self, journey_id):
        return Artifacts()

    async def read_vitals(self):
        return None

    async def storage_state(self):
        return self._state


def _factory(session):
    @asynccontextmanager
    async def make_session(storage_state=None):
        session.seen_state = storage_state
        yield session

    return make_session


async def _noop_sleep(_):
    return None


def test_retry_then_succeed_sets_attempts():
    calls = []

    async def fn(page, ctx):
        calls.append(1)
        async with ctx.step("go"):
            if len(calls) == 1:
                raise RuntimeError("flaky")

    jd = JourneyDef(name="j", journey_id="j", target_host="h", max_age_s=1, interval_s=1, func=fn)
    result = asyncio.run(
        run_journey_resilient(
            jd,
            _factory(_Fake()),
            None,
            worker_id="w",
            executor="playwright",
            executor_version="1.49.0",
            retries=1,
            timeout_s=None,
            sleep=_noop_sleep,
        )
    )
    assert result.status == 0 and result.attempts == 2


def test_exhausts_retries_stays_crit():
    async def fn(page, ctx):
        async with ctx.step("go"):
            raise RuntimeError("always")

    jd = JourneyDef(name="j", journey_id="j", target_host="h", max_age_s=1, interval_s=1, func=fn)
    result = asyncio.run(
        run_journey_resilient(
            jd,
            _factory(_Fake()),
            None,
            worker_id="w",
            executor="playwright",
            executor_version="1.49.0",
            retries=2,
            timeout_s=None,
            sleep=_noop_sleep,
        )
    )
    assert result.status == 2 and result.attempts == 3


def test_timeout_yields_crit_timeouterror():
    async def fn(page, ctx):
        async with ctx.step("hang"):
            await asyncio.sleep(10)

    jd = JourneyDef(name="j", journey_id="j", target_host="h", max_age_s=1, interval_s=1, func=fn)
    result = asyncio.run(
        run_journey_resilient(
            jd,
            _factory(_Fake()),
            None,
            worker_id="w",
            executor="playwright",
            executor_version="1.49.0",
            retries=0,
            timeout_s=0.01,
            sleep=_noop_sleep,
        )
    )
    assert result.status == 2 and result.error.type == "TimeoutError"


def test_run_login_returns_storage_state_and_threads_it():
    async def fn(page, ctx):
        async with ctx.step("signin"):
            pass

    ld = LoginDef(
        name="login", login_id="login", target_host="app", max_age_s=1, interval_s=1, func=fn
    )
    state = {"cookies": [{"name": "sid", "value": "x"}]}
    result, captured = asyncio.run(
        run_login(
            ld,
            _factory(_Fake(state)),
            worker_id="w",
            executor="playwright",
            executor_version="1.49.0",
            retries=0,
            timeout_s=None,
            sleep=_noop_sleep,
        )
    )
    assert result.status == 0 and captured == state


class _VitalsSession:
    page = object()

    def __init__(self, snapshots):
        self._snaps = list(snapshots)

    async def read_vitals(self):
        return self._snaps.pop(0) if self._snaps else None

    async def capture_failure(self, journey_id):
        return Artifacts()


def test_journey_vitals_from_first_page_and_per_step():
    async def fn(page, ctx):
        async with ctx.step("page one"):
            pass
        async with ctx.step("page two"):
            pass

    jd = JourneyDef(name="j", journey_id="j", target_host="h", max_age_s=1, interval_s=1, func=fn)
    session = _VitalsSession([{"LCP": 900.0, "CLS": 0.01}, {"LCP": 1500.0}])
    result = asyncio.run(
        run_journey(jd, session, worker_id="w", executor="playwright", executor_version="1.49.0")
    )
    assert result.vitals.lcp_ms == 900.0 and result.vitals.cls == 0.01  # first page
    assert result.steps[0].vitals.lcp_ms == 900.0
    assert result.steps[1].vitals.lcp_ms == 1500.0


def test_failing_artifact_capture_still_yields_crit_result():
    class CrashedSession(FakeSession):
        async def capture_failure(self, journey_id: str) -> Artifacts:
            raise RuntimeError("Target page, context or browser has been closed")

    async def run(page, ctx):  # noqa: ARG001
        async with ctx.step("open"):
            raise RuntimeError("net::ERR_CONNECTION_REFUSED")

    result = asyncio.run(
        run_journey(
            _jd(run),
            CrashedSession(),
            worker_id="w1",
            executor="playwright",
            executor_version="1.49.0",
        )
    )
    assert result.status == 2
    assert result.error is not None and "ERR_CONNECTION_REFUSED" in result.error.message
    assert result.artifacts == Artifacts()


def test_deadline_stops_retries():
    clock = [0.0]

    async def fn(page, ctx):  # noqa: ARG001
        clock[0] += 50.0
        raise RuntimeError("down")

    result = asyncio.run(
        run_journey_resilient(
            _jd(fn),
            _factory(_Fake()),
            None,
            worker_id="w",
            executor="playwright",
            executor_version="x",
            retries=3,
            timeout_s=None,
            mono=lambda: clock[0],
            sleep=_noop_sleep,
            deadline=40.0,
        )
    )
    assert result.status == 2
    assert result.attempts == 1


def test_deadline_caps_attempt_timeout():
    async def fn(page, ctx):  # noqa: ARG001
        await asyncio.sleep(5)

    result = asyncio.run(
        run_journey_resilient(
            _jd(fn),
            _factory(_Fake()),
            None,
            worker_id="w",
            executor="playwright",
            executor_version="x",
            retries=0,
            timeout_s=120.0,
            sleep=_noop_sleep,
            deadline=time.monotonic() + 0.05,
        )
    )
    assert result.status == 2
    assert result.error is not None and result.error.type == "TimeoutError"

"""Browser-agnostic journey execution: drive a Session, emit a JourneyResult."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from contextlib import AbstractAsyncContextManager
from typing import Any, Protocol

from synmon_contract.models import (
    SCHEMA_VERSION,
    Artifacts,
    JourneyError,
    JourneyResult,
    Status,
    Step,
)

from synmon_executor.sdk import JourneyDef, LoginDef, StepRecorder
from synmon_executor.vitals import to_vitals


class Session(Protocol):
    page: object

    async def capture_failure(self, journey_id: str) -> Artifacts: ...

    # Optional: sessions that support web vitals implement this.
    async def read_vitals(self) -> dict | None: ...

    async def storage_state(self) -> dict: ...


MakeSession = Callable[[dict | None], AbstractAsyncContextManager[Session]]


def _summary(jd: JourneyDef, status: int, error: JourneyError | None, n_steps: int) -> str:
    if status == int(Status.OK):
        return f"{jd.name}: OK ({n_steps} steps)"
    if error is not None:
        return f"{jd.name}: {error.type} at step '{error.step}': {error.message}"
    return f"{jd.name}: status {status}"


async def run_journey(
    jd: JourneyDef,
    session: Session,
    *,
    worker_id: str,
    executor: str,
    executor_version: str,
    wall: Callable[[], float] = time.time,
    mono: Callable[[], float] = time.monotonic,
) -> JourneyResult:
    reader = getattr(session, "read_vitals", None)
    recorder = StepRecorder(wall=wall, mono=mono, vitals_reader=reader)
    started_at = wall()
    t0 = mono()
    status = int(Status.OK)
    error: JourneyError | None = None
    artifacts = Artifacts()

    try:
        await jd.func(session.page, recorder)
    except Exception as exc:
        status = int(Status.CRIT)
        error = JourneyError(
            type=type(exc).__name__,
            message=str(exc),
            step=recorder.last_failed_step,
        )
        # A crashed page/browser makes capture fail too; the CRIT result matters more than the
        # screenshot, so never let artifact capture swallow it.
        try:
            artifacts = await session.capture_failure(jd.journey_id)
        except Exception:
            artifacts = Artifacts()

    duration_ms = int((mono() - t0) * 1000)
    finished_at = wall()
    steps = [
        Step(
            name=s.name,
            status=s.status,
            duration_ms=s.duration_ms,
            message=s.message,
            started_at=s.started_at,
            vitals=to_vitals(s.vitals),
        )
        for s in recorder.steps
    ]
    journey_vitals = next((st.vitals for st in steps if st.vitals is not None), None)
    final_status = max([status, *(s.status for s in steps)])
    return JourneyResult(
        schema_version=SCHEMA_VERSION,
        executor=executor,
        executor_version=executor_version,
        worker_id=worker_id,
        target_host=jd.target_host,
        journey_name=jd.name,
        journey_id=jd.journey_id,
        status=final_status,
        summary=_summary(jd, final_status, error, len(steps)),
        started_at=started_at,
        finished_at=finished_at,
        duration_ms=duration_ms,
        max_age_s=jd.max_age_s,
        interval_s=jd.interval_s,
        steps=steps,
        artifacts=artifacts,
        error=error,
        labels=jd.labels,
        vitals=journey_vitals,
    )


def _timeout_result(
    jd: JourneyDef | LoginDef,
    *,
    worker_id: str,
    executor: str,
    executor_version: str,
    started_at: float,
    wall: Callable[[], float],
    timeout_s: float,
) -> JourneyResult:
    return JourneyResult(
        schema_version=SCHEMA_VERSION,
        executor=executor,
        executor_version=executor_version,
        worker_id=worker_id,
        target_host=jd.target_host,
        journey_name=jd.name,
        journey_id=jd.journey_id,
        status=int(Status.CRIT),
        summary=f"{jd.name}: TimeoutError after {timeout_s}s",
        started_at=started_at,
        finished_at=wall(),
        duration_ms=int(timeout_s * 1000),
        max_age_s=jd.max_age_s,
        interval_s=jd.interval_s,
        steps=[],
        artifacts=Artifacts(),
        error=JourneyError(type="TimeoutError", message=f"exceeded {timeout_s}s", step=None),
        labels=jd.labels,
    )


def unknown_result(
    jd: JourneyDef | LoginDef,
    *,
    worker_id: str,
    executor: str,
    executor_version: str,
    reason: str,
    wall: Callable[[], float] = time.time,
) -> JourneyResult:
    """UNKNOWN result for a journey without a conclusive run: it never shows a stale OK and is
    not counted as a target outage."""
    now = wall()
    return JourneyResult(
        schema_version=SCHEMA_VERSION,
        executor=executor,
        executor_version=executor_version,
        worker_id=worker_id,
        target_host=jd.target_host,
        journey_name=jd.name,
        journey_id=jd.journey_id,
        status=int(Status.UNKNOWN),
        summary=f"{jd.name}: {reason}",
        started_at=now,
        finished_at=now,
        duration_ms=0,
        max_age_s=jd.max_age_s,
        interval_s=jd.interval_s,
        labels=jd.labels,
    )


async def _attempt(
    jd: JourneyDef | LoginDef,
    session: Session,
    *,
    worker_id: str,
    executor: str,
    executor_version: str,
    timeout_s: float | None,
    wall: Callable[[], float],
    mono: Callable[[], float],
    budget_bound: bool = False,
) -> JourneyResult | None:
    """Run one attempt; ``None`` means the run budget (not the journey timeout) cut it short."""
    started_at = wall()
    coro = run_journey(
        jd,  # type: ignore[arg-type]
        session,
        worker_id=worker_id,
        executor=executor,
        executor_version=executor_version,
        wall=wall,
        mono=mono,
    )
    if timeout_s is None:
        return await coro
    try:
        return await asyncio.wait_for(coro, timeout_s)
    except TimeoutError:
        if budget_bound:
            return None
        return _timeout_result(
            jd,
            worker_id=worker_id,
            executor=executor,
            executor_version=executor_version,
            started_at=started_at,
            wall=wall,
            timeout_s=timeout_s,
        )


async def _resilient(
    jd: JourneyDef | LoginDef,
    make_session: MakeSession,
    storage_state: dict | None,
    *,
    worker_id: str,
    executor: str,
    executor_version: str,
    retries: int,
    timeout_s: float | None,
    wall: Callable[[], float],
    mono: Callable[[], float],
    sleep: Callable[[float], Awaitable[Any]],
    capture_state: bool,
    backoff_base: float = 1.0,
    deadline: float | None = None,
) -> tuple[JourneyResult, dict | None]:
    result: JourneyResult | None = None
    captured: dict | None = None
    attempts = 0
    for attempt in range(1, retries + 2):
        attempt_timeout = timeout_s
        budget_bound = False
        if deadline is not None:
            remaining = max(deadline - mono(), 0.0)
            if timeout_s is None or remaining < timeout_s:
                attempt_timeout, budget_bound = remaining, True
        async with make_session(storage_state) as session:
            attempt_result = await _attempt(
                jd,
                session,
                worker_id=worker_id,
                executor=executor,
                executor_version=executor_version,
                timeout_s=attempt_timeout,
                wall=wall,
                mono=mono,
                budget_bound=budget_bound,
            )
            if (
                capture_state
                and attempt_result is not None
                and attempt_result.status < int(Status.CRIT)
            ):
                captured = await session.storage_state()
        if attempt_result is None:
            # Out of time says nothing about the target; keep a failure already observed.
            if result is None:
                result = unknown_result(
                    jd,
                    worker_id=worker_id,
                    executor=executor,
                    executor_version=executor_version,
                    reason="cut short, run budget exhausted",
                    wall=wall,
                )
                attempts = attempt
            break
        result, attempts = attempt_result, attempt
        if result.status < int(Status.CRIT) or attempt > retries:
            break
        backoff = backoff_base * (2 ** (attempt - 1))
        if deadline is not None and mono() + backoff >= deadline:
            break
        await sleep(backoff)
    assert result is not None
    result = result.model_copy(update={"attempts": attempts})
    return result, captured


async def run_journey_resilient(
    jd: JourneyDef,
    make_session: MakeSession,
    storage_state: dict | None,
    *,
    worker_id: str,
    executor: str,
    executor_version: str,
    retries: int,
    timeout_s: float | None,
    wall: Callable[[], float] = time.time,
    mono: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], Awaitable[Any]] = asyncio.sleep,
    backoff_base: float = 1.0,
    deadline: float | None = None,
) -> JourneyResult:
    result, _ = await _resilient(
        jd,
        make_session,
        storage_state,
        worker_id=worker_id,
        executor=executor,
        executor_version=executor_version,
        retries=retries,
        timeout_s=timeout_s,
        wall=wall,
        mono=mono,
        sleep=sleep,
        capture_state=False,
        backoff_base=backoff_base,
        deadline=deadline,
    )
    return result


async def run_login(
    login_def: LoginDef,
    make_session: MakeSession,
    *,
    worker_id: str,
    executor: str,
    executor_version: str,
    retries: int,
    timeout_s: float | None,
    wall: Callable[[], float] = time.time,
    mono: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], Awaitable[Any]] = asyncio.sleep,
    backoff_base: float = 1.0,
    deadline: float | None = None,
) -> tuple[JourneyResult, dict | None]:
    return await _resilient(
        login_def,
        make_session,
        None,
        worker_id=worker_id,
        executor=executor,
        executor_version=executor_version,
        retries=retries,
        timeout_s=timeout_s,
        wall=wall,
        mono=mono,
        sleep=sleep,
        capture_state=True,
        backoff_base=backoff_base,
        deadline=deadline,
    )

"""Executor entrypoint: discover journeys, run each, write spool + heartbeat."""

from __future__ import annotations

import asyncio
import contextlib
import os
import time
from pathlib import Path

from synmon_contract.models import SCHEMA_VERSION, Heartbeat

from synmon_executor.core import run_journey_resilient, run_login, unknown_result
from synmon_executor.discovery import load_journeys
from synmon_executor.heartbeat import write_heartbeat_atomic
from synmon_executor.sdk import clear_registry, registered_journeys, registered_logins
from synmon_executor.spool import write_result_atomic

EXECUTOR = "playwright"


def _executor_version() -> str:
    try:
        from importlib.metadata import version

        return version("playwright")
    except Exception:
        return "unknown"


async def run_all(
    *,
    journeys_dir: Path,
    spool_dir: Path,
    artifacts_dir: Path,
    heartbeat_path: Path,
    worker_id: str,
    browser_session,
    default_retries: int = 1,
    default_timeout_s: float | None = 120.0,
    default_backoff_s: float = 1.0,
    run_budget_s: float | None = None,
) -> Heartbeat:
    executor_version = _executor_version()
    run_started = time.time()
    t0 = time.monotonic()
    journeys_run = 0
    journeys_failed = 0
    journeys_skipped = 0
    load_errors: list[str] = []
    # Finish (and write the heartbeat) before systemd's hard stop, even while targets hang.
    deadline = t0 + run_budget_s if run_budget_s is not None else None

    def _out_of_budget() -> bool:
        return deadline is not None and time.monotonic() >= deadline

    def _write_unknown(obj, reason: str) -> None:
        result = unknown_result(
            obj,
            worker_id=worker_id,
            executor=EXECUTOR,
            executor_version=executor_version,
            reason=reason,
        )
        # Best effort: if the spool itself is unwritable, the heartbeat still reports the run.
        with contextlib.suppress(Exception):
            write_result_atomic(result, spool_dir)

    def _skip(obj) -> None:
        nonlocal journeys_skipped
        journeys_skipped += 1
        _write_unknown(obj, f"skipped, run budget of {run_budget_s}s exhausted")

    def _executor_error(obj, exc: Exception) -> None:
        nonlocal journeys_failed
        journeys_failed += 1
        _write_unknown(obj, f"executor error: {type(exc).__name__}: {exc}")

    def _retries(obj) -> int:
        return obj.retries if obj.retries is not None else default_retries

    def _timeout(obj) -> float | None:
        return obj.timeout_s if obj.timeout_s is not None else default_timeout_s

    try:
        clear_registry()
        _, load_errors = load_journeys(journeys_dir)
        logins = registered_logins()
        journeys = registered_journeys()
        async with browser_session(artifacts_dir) as make_session:
            storage_states: dict[str, dict] = {}
            failed_logins: dict[str, str] = {}
            for ld in logins:
                if _out_of_budget():
                    _skip(ld)
                    continue
                journeys_run += 1
                try:
                    result, state = await run_login(
                        ld,
                        make_session,
                        worker_id=worker_id,
                        executor=EXECUTOR,
                        executor_version=executor_version,
                        retries=_retries(ld),
                        timeout_s=_timeout(ld),
                        backoff_base=default_backoff_s,
                        deadline=deadline,
                    )
                    write_result_atomic(result, spool_dir)
                    if result.status >= 2:
                        journeys_failed += 1
                        failed_logins[ld.target_host] = ld.name
                    elif state is not None:
                        storage_states[ld.target_host] = state
                except Exception as exc:
                    _executor_error(ld, exc)
                    failed_logins[ld.target_host] = ld.name
            for jd in journeys:
                if _out_of_budget():
                    _skip(jd)
                    continue
                if jd.target_host in failed_logins:
                    # Unauthenticated runs would only repeat the login outage as extra CRITs.
                    _write_unknown(
                        jd, f"skipped, login '{failed_logins[jd.target_host]}' did not succeed"
                    )
                    continue
                journeys_run += 1
                try:
                    result = await run_journey_resilient(
                        jd,
                        make_session,
                        storage_states.get(jd.target_host),
                        worker_id=worker_id,
                        executor=EXECUTOR,
                        executor_version=executor_version,
                        retries=_retries(jd),
                        timeout_s=_timeout(jd),
                        backoff_base=default_backoff_s,
                        deadline=deadline,
                    )
                    write_result_atomic(result, spool_dir)
                    if result.status >= 2:
                        journeys_failed += 1
                except Exception as exc:
                    _executor_error(jd, exc)
    finally:
        hb = Heartbeat(
            schema_version=SCHEMA_VERSION,
            worker_id=worker_id,
            executor=EXECUTOR,
            executor_version=executor_version,
            heartbeat_at=time.time(),
            last_run_started_at=run_started,
            last_run_finished_at=time.time(),
            last_run_duration_ms=int((time.monotonic() - t0) * 1000),
            journeys_run=journeys_run,
            journeys_failed=journeys_failed,
            journeys_skipped=journeys_skipped,
            load_errors=load_errors,
        )
        write_heartbeat_atomic(hb, heartbeat_path)
    return hb


def main() -> None:
    from synmon_executor.playwright_session import browser_session

    worker_id = os.environ.get("SYNMON_WORKER_ID") or os.uname().nodename
    budget = os.environ.get("SYNMON_RUN_BUDGET_S")
    asyncio.run(
        run_all(
            journeys_dir=Path(os.environ.get("SYNMON_JOURNEYS_DIR", "/journeys")),
            spool_dir=Path(os.environ.get("SYNMON_SPOOL_DIR", "/var/lib/synmon/spool")),
            artifacts_dir=Path(os.environ.get("SYNMON_ARTIFACTS_DIR", "/var/lib/synmon/artifacts")),
            heartbeat_path=Path(
                os.environ.get("SYNMON_HEARTBEAT_PATH", "/var/lib/synmon/heartbeat.json")
            ),
            worker_id=worker_id,
            browser_session=browser_session,
            default_retries=int(os.environ.get("SYNMON_RETRIES", "1")),
            default_timeout_s=float(os.environ.get("SYNMON_TIMEOUT_S", "120")),
            default_backoff_s=float(os.environ.get("SYNMON_RETRY_BACKOFF_S", "1.0")),
            run_budget_s=float(budget) if budget else None,
        )
    )


if __name__ == "__main__":
    main()

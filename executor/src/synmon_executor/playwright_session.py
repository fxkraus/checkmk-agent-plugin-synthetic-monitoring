"""Real Playwright session adapter (integration only; lazy import so unit tests stay offline)."""

from __future__ import annotations

import contextlib
import os
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from synmon_contract.models import Artifacts

# Artifacts can show whatever the page showed; keep them away from "other" (dir is 2750 too).
_ARTIFACT_MODE = 0o640


class PlaywrightSession:
    def __init__(
        self, context: object, page: object, artifacts_dir: Path, *, tracing: bool = False
    ) -> None:
        self._context = context
        self.page = page
        self._artifacts_dir = artifacts_dir
        self._tracing = tracing

    async def capture_failure(self, name: str) -> Artifacts:
        self._artifacts_dir.mkdir(parents=True, exist_ok=True)
        shot = self._artifacts_dir / f"{name}.png"
        await self.page.screenshot(path=str(shot), full_page=True)  # type: ignore[attr-defined]
        os.chmod(shot, _ARTIFACT_MODE)
        trace_path = None
        if self._tracing:
            self._tracing = False
            trace = self._artifacts_dir / f"{name}.trace.zip"
            await self._context.tracing.stop(path=str(trace))  # type: ignore[attr-defined]
            os.chmod(trace, _ARTIFACT_MODE)
            trace_path = str(trace)
        return Artifacts(screenshot_path=str(shot), trace_path=trace_path)

    async def read_vitals(self) -> dict | None:
        try:
            return await self.page.evaluate("() => window.__synmon_vitals || null")  # type: ignore[attr-defined]
        except Exception:
            return None

    async def storage_state(self) -> dict:
        return await self._context.storage_state()  # type: ignore[attr-defined]

    async def discard_trace(self) -> None:
        if self._tracing:
            self._tracing = False
            await self._context.tracing.stop()  # type: ignore[attr-defined]


async def _inject_vitals(context: object) -> None:
    """Best-effort Web Vitals injection; any failure is silently ignored."""
    try:
        from synmon_executor.vitals import build_init_script, load_vendored_lib

        await context.add_init_script(script=build_init_script(load_vendored_lib()))  # type: ignore[attr-defined]
    except Exception:
        pass


def _session_factory(
    launch: Callable[[], Awaitable[Any]], browser: Any, artifacts_dir: Path, *, trace: bool
):
    """Build the make_session CM; relaunches the browser if a previous journey crashed it."""
    current = browser

    @asynccontextmanager
    async def make_session(storage_state: dict | None = None):
        nonlocal current
        if not current.is_connected():
            with contextlib.suppress(Exception):
                await current.close()
            current = await launch()
        context = await current.new_context(storage_state=storage_state)
        session: PlaywrightSession | None = None
        try:
            await _inject_vitals(context)
            if trace:
                await context.tracing.start(screenshots=True, snapshots=True)
            page = await context.new_page()
            session = PlaywrightSession(context, page, artifacts_dir, tracing=trace)
            yield session
        finally:
            # A crashed browser makes teardown fail too; that must not replace the result.
            if session is not None:
                with contextlib.suppress(Exception):
                    await session.discard_trace()
            with contextlib.suppress(Exception):
                await context.close()

    def latest() -> Any:
        return current

    return make_session, latest


@asynccontextmanager
async def browser_session(
    artifacts_dir: Path,
    *,
    headless: bool = True,
    trace: bool = False,
    chromium_sandbox: bool = False,
):
    """Browser-once session provider: yields a make_session factory.

    The factory is an async CM accepting an optional storage_state dict. Each call opens a new
    browser context (optionally pre-seeded with storage_state) and cleans up on exit.

    ``trace`` records a Playwright trace and saves it on failure. Traces contain typed values
    (passwords) and request headers/bodies (session cookies), so it is off by default.

    ``chromium_sandbox`` turns on Chromium's own sandbox (Playwright disables it by default).
    Without it the container is the only isolation from the monitored pages.
    """
    from playwright.async_api import async_playwright

    async with async_playwright() as pw:

        async def launch() -> Any:
            return await pw.chromium.launch(headless=headless, chromium_sandbox=chromium_sandbox)

        make_session, latest = _session_factory(launch, await launch(), artifacts_dir, trace=trace)
        try:
            yield make_session
        finally:
            with contextlib.suppress(Exception):
                await latest().close()

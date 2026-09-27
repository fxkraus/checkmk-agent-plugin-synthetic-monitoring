"""Real Playwright session adapter (integration only; lazy import so unit tests stay offline)."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from synmon_contract.models import Artifacts


class PlaywrightSession:
    def __init__(self, context: object, page: object, artifacts_dir: Path) -> None:
        self._context = context
        self.page = page
        self._artifacts_dir = artifacts_dir
        self._trace_stopped = False

    async def capture_failure(self, journey_id: str) -> Artifacts:
        self._artifacts_dir.mkdir(parents=True, exist_ok=True)
        shot = self._artifacts_dir / f"{journey_id}.png"
        await self.page.screenshot(path=str(shot), full_page=True)  # type: ignore[attr-defined]
        trace = self._artifacts_dir / f"{journey_id}.trace.zip"
        await self._context.tracing.stop(path=str(trace))  # type: ignore[attr-defined]
        self._trace_stopped = True
        return Artifacts(screenshot_path=str(shot), trace_path=str(trace))

    async def read_vitals(self) -> dict | None:
        try:
            return await self.page.evaluate("() => window.__synmon_vitals || null")  # type: ignore[attr-defined]
        except Exception:
            return None

    async def storage_state(self) -> dict:
        return await self._context.storage_state()  # type: ignore[attr-defined]

    async def discard_trace(self) -> None:
        if not self._trace_stopped:
            await self._context.tracing.stop()  # type: ignore[attr-defined]
            self._trace_stopped = True


async def _inject_vitals(context: object) -> None:
    """Best-effort Web Vitals injection; any failure is silently ignored."""
    try:
        from synmon_executor.vitals import build_init_script, load_vendored_lib

        await context.add_init_script(script=build_init_script(load_vendored_lib()))  # type: ignore[attr-defined]
    except Exception:
        pass


@asynccontextmanager
async def browser_session(artifacts_dir: Path, *, headless: bool = True):
    """Browser-once session provider: yields a make_session factory.

    The factory is an async CM accepting an optional storage_state dict.
    Each call opens a new browser context (optionally pre-seeded with
    storage_state), runs tracing, and cleans up on exit.
    """
    from playwright.async_api import async_playwright

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=headless)
        try:

            @asynccontextmanager
            async def make_session(storage_state: dict | None = None):
                context = await browser.new_context(storage_state=storage_state)  # type: ignore[arg-type]
                await _inject_vitals(context)
                await context.tracing.start(screenshots=True, snapshots=True)
                page = await context.new_page()
                session = PlaywrightSession(context, page, artifacts_dir)
                try:
                    yield session
                finally:
                    await session.discard_trace()
                    await context.close()

            yield make_session
        finally:
            await browser.close()

import asyncio
import stat

from synmon_executor.playwright_session import (
    PlaywrightSession,
    _inject_vitals,
    _session_factory,
)


class _FakePage:
    def __init__(self, value):
        self._value = value

    async def evaluate(self, _script):
        return self._value


def test_read_vitals_returns_snapshot():
    sess = PlaywrightSession(context=object(), page=_FakePage({"LCP": 1.0}), artifacts_dir=None)
    assert asyncio.run(sess.read_vitals()) == {"LCP": 1.0}


def test_read_vitals_swallows_errors():
    class _Boom:
        async def evaluate(self, _):
            raise RuntimeError("no page")

    sess = PlaywrightSession(context=object(), page=_Boom(), artifacts_dir=None)
    assert asyncio.run(sess.read_vitals()) is None


def test_inject_vitals_does_not_propagate_on_failure():
    """_inject_vitals must be best-effort: a failing add_init_script must not raise."""

    class _BoomContext:
        async def add_init_script(self, *, script: str) -> None:
            raise FileNotFoundError("vendored lib missing")

    # Must complete without raising, even when add_init_script raises.
    asyncio.run(_inject_vitals(_BoomContext()))


def test_inject_vitals_does_not_propagate_on_load_error(monkeypatch):
    """_inject_vitals must be best-effort: a missing vendored asset must not raise."""
    import synmon_executor.vitals as vitals_mod

    def _boom():
        raise FileNotFoundError("web-vitals.iife.js not found")

    monkeypatch.setattr(vitals_mod, "load_vendored_lib", _boom)

    class _FakeContext:
        called = False

        async def add_init_script(self, *, script: str) -> None:
            _FakeContext.called = True

    ctx = _FakeContext()
    asyncio.run(_inject_vitals(ctx))
    assert not ctx.called  # injection was aborted before reaching add_init_script


def test_storage_state_delegates_to_context():
    class _Ctx:
        async def storage_state(self):
            return {"cookies": [1]}

    sess = PlaywrightSession(context=_Ctx(), page=object(), artifacts_dir=None)
    assert asyncio.run(sess.storage_state()) == {"cookies": [1]}


class _Tracing:
    def __init__(self, fail_stop: bool = False) -> None:
        self.started = False
        self.stops: list[str | None] = []
        self._fail_stop = fail_stop

    async def start(self, **_kw):
        self.started = True

    async def stop(self, path=None):
        self.stops.append(path)
        if self._fail_stop:
            raise RuntimeError("Target closed")
        if path:
            open(path, "wb").close()


class _ShotPage:
    async def screenshot(self, *, path, full_page):  # noqa: ARG002
        open(path, "wb").close()

    async def evaluate(self, _):
        return None


class _Context:
    def __init__(self, tracing: _Tracing) -> None:
        self.tracing = tracing
        self.closed = False

    async def add_init_script(self, *, script):  # noqa: ARG002
        return None

    async def new_page(self):
        return _ShotPage()

    async def close(self):
        self.closed = True


class _Browser:
    def __init__(self, tracing: _Tracing, connected: bool = True) -> None:
        self.tracing = tracing
        self.connected = connected
        self.contexts: list[_Context] = []

    def is_connected(self):
        return self.connected

    async def new_context(self, storage_state=None):  # noqa: ARG002
        ctx = _Context(self.tracing)
        self.contexts.append(ctx)
        return ctx

    async def close(self):
        self.connected = False


def test_capture_failure_saves_only_a_restricted_screenshot_without_trace(tmp_path):
    sess = PlaywrightSession(_Context(_Tracing()), _ShotPage(), tmp_path)
    artifacts = asyncio.run(sess.capture_failure("app.example.com__login"))
    assert artifacts.trace_path is None
    shot = tmp_path / "app.example.com__login.png"
    assert artifacts.screenshot_path == str(shot)
    assert stat.S_IMODE(shot.stat().st_mode) == 0o640
    assert list(tmp_path.iterdir()) == [shot]


def test_capture_failure_saves_trace_when_tracing(tmp_path):
    tracing = _Tracing()
    sess = PlaywrightSession(_Context(tracing), _ShotPage(), tmp_path, tracing=True)
    artifacts = asyncio.run(sess.capture_failure("h__j"))
    assert artifacts.trace_path == str(tmp_path / "h__j.trace.zip")
    assert stat.S_IMODE((tmp_path / "h__j.trace.zip").stat().st_mode) == 0o640
    asyncio.run(sess.discard_trace())  # already saved: no second stop
    assert tracing.stops == [artifacts.trace_path]


def _use(make_session):
    async def go():
        async with make_session(None) as session:
            return session

    return asyncio.run(go())


async def _no_launch():
    raise AssertionError("must not relaunch")


def test_no_trace_is_recorded_when_tracing_is_disabled(tmp_path):
    tracing = _Tracing()
    browser = _Browser(tracing)
    make_session, _ = _session_factory(_no_launch, browser, tmp_path, trace=False)
    _use(make_session)
    assert not tracing.started and tracing.stops == []
    assert browser.contexts[0].closed


def test_failing_trace_teardown_still_closes_and_does_not_raise(tmp_path):
    tracing = _Tracing(fail_stop=True)
    browser = _Browser(tracing)
    make_session, _ = _session_factory(_no_launch, browser, tmp_path, trace=True)
    _use(make_session)
    assert tracing.started
    assert browser.contexts[0].closed


def test_disconnected_browser_is_relaunched(tmp_path):
    crashed = _Browser(_Tracing(), connected=False)
    fresh = _Browser(_Tracing())

    async def launch():
        return fresh

    make_session, latest = _session_factory(launch, crashed, tmp_path, trace=False)
    _use(make_session)
    assert latest() is fresh and len(fresh.contexts) == 1 and crashed.contexts == []


def test_browser_session_passes_the_sandbox_flag_to_chromium(tmp_path, monkeypatch):
    import playwright.async_api
    from synmon_executor.playwright_session import browser_session

    launches = []

    class _Chromium:
        async def launch(self, **kwargs):
            launches.append(kwargs)
            return _Browser(_Tracing())

    class _Playwright:
        chromium = _Chromium()

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

    monkeypatch.setattr(playwright.async_api, "async_playwright", _Playwright)

    async def go(**kwargs):
        async with browser_session(tmp_path, **kwargs):
            pass

    asyncio.run(go())
    asyncio.run(go(chromium_sandbox=True))
    assert [k["chromium_sandbox"] for k in launches] == [False, True]

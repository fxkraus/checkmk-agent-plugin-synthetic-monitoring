import asyncio

from synmon_executor.playwright_session import PlaywrightSession, _inject_vitals


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

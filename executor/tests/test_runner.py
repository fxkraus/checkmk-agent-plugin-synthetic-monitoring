import asyncio
import json
from contextlib import asynccontextmanager

from synmon_contract.models import Artifacts
from synmon_executor.runner import run_all
from synmon_executor.sdk import clear_registry

JOURNEY_OK = """
from synmon_executor import journey

@journey(name="ok", target_host="a.example.com", max_age_s=600, interval_s=300)
async def run(page, ctx):
    async with ctx.step("noop"):
        pass
"""

JOURNEY_FAIL = """
from synmon_executor import journey

@journey(name="bad", target_host="b.example.com", max_age_s=600, interval_s=300)
async def run(page, ctx):
    async with ctx.step("boom"):
        raise RuntimeError("kaboom")
"""

# Raises inside a step so run_journey_resilient catches it as CRIT (journeys_failed).
JOURNEY_CRASH = """
from synmon_executor import journey

@journey(name="crash", target_host="c.example.com", max_age_s=600, interval_s=300)
async def run(page, ctx):
    async with ctx.step("boom"):
        raise RuntimeError("kaboom")
"""

LOGIN_FILE = """\
from synmon_executor import login

@login(target_host="app", name="login", max_age_s=1, interval_s=1)
async def _login(page, ctx):
    async with ctx.step("signin"):
        pass
"""

JOURNEY_HOME = """\
from synmon_executor import journey

@journey(name="home", target_host="app", max_age_s=1, interval_s=1)
async def _home(page, ctx):
    async with ctx.step("open"):
        pass
"""


class FakeSession:
    def __init__(self):
        self.page = object()

    async def capture_failure(self, journey_id):
        return Artifacts(screenshot_path=f"/a/{journey_id}.png")

    async def read_vitals(self):
        return None

    async def storage_state(self):
        return {}


def _fake_browser_session():
    @asynccontextmanager
    async def browser_session(artifacts_dir):
        @asynccontextmanager
        async def make_session(storage_state=None):
            yield FakeSession()

        yield make_session

    return browser_session


def test_run_all_isolates_journey_failure_and_always_writes_heartbeat(tmp_path):
    clear_registry()
    jdir = tmp_path / "journeys"
    jdir.mkdir()
    (jdir / "ok.py").write_text(JOURNEY_OK, encoding="utf-8")
    (jdir / "crash.py").write_text(JOURNEY_CRASH, encoding="utf-8")
    spool = tmp_path / "spool"
    artifacts = tmp_path / "artifacts"
    hb_path = tmp_path / "heartbeat.json"

    hb = asyncio.run(
        run_all(
            journeys_dir=jdir,
            spool_dir=spool,
            artifacts_dir=artifacts,
            heartbeat_path=hb_path,
            worker_id="w1",
            browser_session=_fake_browser_session(),
        )
    )

    # Heartbeat file must exist and record the failure
    assert hb_path.exists(), "heartbeat.json was never written"
    assert hb.journeys_failed >= 1

    # The non-crashing journey's spool file must have been written
    assert (spool / "a.example.com__ok.json").exists(), "ok journey spool not written"


def test_run_all_writes_spool_and_heartbeat(tmp_path):
    clear_registry()
    jdir = tmp_path / "journeys"
    jdir.mkdir()
    (jdir / "ok.py").write_text(JOURNEY_OK, encoding="utf-8")
    (jdir / "fail.py").write_text(JOURNEY_FAIL, encoding="utf-8")
    spool = tmp_path / "spool"
    artifacts = tmp_path / "artifacts"
    hb_path = tmp_path / "heartbeat.json"

    hb = asyncio.run(
        run_all(
            journeys_dir=jdir,
            spool_dir=spool,
            artifacts_dir=artifacts,
            heartbeat_path=hb_path,
            worker_id="w1",
            browser_session=_fake_browser_session(),
        )
    )

    files = sorted(p.name for p in spool.glob("*.json"))
    assert files == ["a.example.com__ok.json", "b.example.com__bad.json"]
    ok = json.loads((spool / "a.example.com__ok.json").read_text("utf-8"))
    bad = json.loads((spool / "b.example.com__bad.json").read_text("utf-8"))
    assert ok["status"] == 0 and bad["status"] == 2
    assert hb.journeys_run == 2 and hb.journeys_failed == 1
    assert json.loads(hb_path.read_text("utf-8"))["journeys_failed"] == 1


def test_run_all_runs_login_first_and_threads_storage_state(tmp_path):
    seen = {}

    state = {"cookies": [{"name": "sid", "value": "x"}]}

    class _Fake:
        page = object()

        async def capture_failure(self, jid):
            return Artifacts()

        async def read_vitals(self):
            return None

        async def storage_state(self):
            return state

    @asynccontextmanager
    async def browser_session(artifacts_dir):
        @asynccontextmanager
        async def make_session(storage_state=None):
            seen.setdefault("states", []).append(storage_state)
            yield _Fake()

        yield make_session

    jdir = tmp_path / "journeys"
    jdir.mkdir()
    (jdir / "login_app.py").write_text(LOGIN_FILE, encoding="utf-8")
    (jdir / "journey_home.py").write_text(JOURNEY_HOME, encoding="utf-8")

    hb = asyncio.run(
        run_all(
            journeys_dir=jdir,
            spool_dir=tmp_path / "spool",
            artifacts_dir=tmp_path / "art",
            heartbeat_path=tmp_path / "hb.json",
            worker_id="w",
            browser_session=browser_session,
        )
    )
    # login ran first (storage_state=None), home ran with the captured login storage_state
    assert seen["states"] == [None, state]
    assert hb.journeys_run == 2


def test_run_all_survives_broken_journey_file(tmp_path):
    clear_registry()
    jdir = tmp_path / "journeys"
    jdir.mkdir()
    (jdir / "broken.py").write_text("raise ImportError('no such module')\n", encoding="utf-8")
    (jdir / "ok.py").write_text(JOURNEY_OK, encoding="utf-8")
    spool = tmp_path / "spool"
    hb_path = tmp_path / "heartbeat.json"

    hb = asyncio.run(
        run_all(
            journeys_dir=jdir,
            spool_dir=spool,
            artifacts_dir=tmp_path / "artifacts",
            heartbeat_path=hb_path,
            worker_id="w1",
            browser_session=_fake_browser_session(),
        )
    )

    assert (spool / "a.example.com__ok.json").exists()
    assert hb.load_errors == ["broken.py: ImportError: no such module"]
    assert json.loads(hb_path.read_text("utf-8"))["load_errors"] == hb.load_errors


JOURNEY_SLOW = """
import asyncio
from synmon_executor import journey

@journey(name="slow", target_host="a.example.com", max_age_s=600, interval_s=300)
async def run(page, ctx):
    async with ctx.step("hang"):
        await asyncio.sleep(5)
"""

JOURNEY_LATER = """
from synmon_executor import journey

@journey(name="later", target_host="b.example.com", max_age_s=600, interval_s=300)
async def run(page, ctx):
    async with ctx.step("noop"):
        pass
"""


def test_run_budget_marks_unrun_journeys_skipped(tmp_path):
    clear_registry()
    jdir = tmp_path / "journeys"
    jdir.mkdir()
    (jdir / "a_slow.py").write_text(JOURNEY_SLOW, encoding="utf-8")
    (jdir / "b_later.py").write_text(JOURNEY_LATER, encoding="utf-8")
    spool = tmp_path / "spool"
    hb_path = tmp_path / "heartbeat.json"

    hb = asyncio.run(
        run_all(
            journeys_dir=jdir,
            spool_dir=spool,
            artifacts_dir=tmp_path / "artifacts",
            heartbeat_path=hb_path,
            worker_id="w1",
            browser_session=_fake_browser_session(),
            default_retries=2,
            run_budget_s=0.1,
        )
    )

    slow = json.loads((spool / "a.example.com__slow.json").read_text("utf-8"))
    later = json.loads((spool / "b.example.com__later.json").read_text("utf-8"))
    assert slow["status"] == 2 and slow["error"]["type"] == "TimeoutError"
    assert later["status"] == 3 and "run budget" in later["summary"]
    assert hb_path.exists()
    assert hb.journeys_run == 1 and hb.journeys_skipped == 1

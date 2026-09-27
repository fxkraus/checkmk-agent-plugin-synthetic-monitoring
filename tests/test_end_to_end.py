import asyncio
import importlib.util
import io
import json
from contextlib import asynccontextmanager
from pathlib import Path

import jsonschema
from synmon_contract.models import Artifacts, JourneyResult, WorkerHealth
from synmon_executor.runner import run_all
from synmon_executor.sdk import clear_registry

REPO = Path(__file__).resolve().parents[1]
PLUGIN = REPO / "agent_plugin" / "synmon_collector.py"

JOURNEY = """
from synmon_executor import journey

@journey(name="login", target_host="app.example.com", max_age_s=900, interval_s=300)
async def run(page, ctx):
    async with ctx.step("open"):
        pass
"""


class FakeSession:
    def __init__(self):
        self.page = object()

    async def capture_failure(self, journey_id):
        return Artifacts()

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


def _load_plugin():
    assert PLUGIN.exists(), f"Agent plugin not found: {PLUGIN}"
    spec = importlib.util.spec_from_file_location("synmon_collector", PLUGIN)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_executor_output_flows_through_agent_and_validates(tmp_path):
    clear_registry()
    jdir = tmp_path / "journeys"
    jdir.mkdir()
    (jdir / "login.py").write_text(JOURNEY, encoding="utf-8")
    spool = tmp_path / "spool"
    hb_path = tmp_path / "heartbeat.json"

    asyncio.run(
        run_all(
            journeys_dir=jdir,
            spool_dir=spool,
            artifacts_dir=tmp_path / "artifacts",
            heartbeat_path=hb_path,
            worker_id="w1",
            browser_session=_fake_browser_session(),
        )
    )

    plugin = _load_plugin()
    buf = io.StringIO()
    plugin.main(spool_dir=spool, heartbeat_path=hb_path, out=buf)
    lines = buf.getvalue().splitlines()

    result_schema = json.loads((REPO / "schema" / "synmon_result.schema.json").read_text("utf-8"))
    worker_schema = json.loads((REPO / "schema" / "synmon_worker.schema.json").read_text("utf-8"))

    w_idx = lines.index("<<<synmon_worker:sep(0)>>>")
    worker_payload = json.loads(lines[w_idx + 1])
    jsonschema.validate(worker_payload, worker_schema)
    WorkerHealth.model_validate(worker_payload)

    j_idx = lines.index("<<<synmon_journey:sep(0)>>>")
    journey_payload = json.loads(lines[j_idx + 1])
    jsonschema.validate(journey_payload, result_schema)
    parsed = JourneyResult.model_validate(journey_payload)
    assert parsed.journey_name == "login" and parsed.status == 0

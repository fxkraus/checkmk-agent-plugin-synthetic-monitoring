import os

import pytest

if not os.environ.get("SYNMON_INTEGRATION"):
    pytest.skip("set SYNMON_INTEGRATION=1 to run live browser tests", allow_module_level=True)

# heavy imports below this line
import asyncio
import json
from pathlib import Path

from synmon_executor.playwright_session import browser_session
from synmon_executor.runner import run_all

_JOURNEYS = Path(__file__).resolve().parent / "journeys"


def _run(tmp_path):
    spool = tmp_path / "spool"
    asyncio.run(
        run_all(
            journeys_dir=_JOURNEYS,
            spool_dir=spool,
            artifacts_dir=tmp_path / "art",
            heartbeat_path=tmp_path / "hb.json",
            worker_id="it",
            browser_session=browser_session,
            default_retries=1,
            default_timeout_s=30.0,
            default_backoff_s=0.0,
        )
    )
    results = {}
    for f in spool.glob("*.json"):
        obj = json.loads(f.read_text())
        results[obj["journey_name"]] = obj
    return results


def test_live_pipeline(tmp_path):
    r = _run(tmp_path)
    # home: passes, vitals captured (LCP/FCP/TTFB at least)
    assert r["home"]["status"] == 0
    v = r["home"]["vitals"]
    assert v and (v.get("lcp_ms") or v.get("fcp_ms") or v.get("ttfb_ms"))
    # login monitored + protected reachable via reused storage_state
    assert r["login"]["status"] == 0
    assert r["protected"]["status"] == 0
    # flaky recovered via retry
    assert r["flaky"]["status"] == 0 and r["flaky"]["attempts"] >= 2
    # slow timed out
    assert r["slow"]["status"] == 2 and r["slow"]["error"]["type"] == "TimeoutError"

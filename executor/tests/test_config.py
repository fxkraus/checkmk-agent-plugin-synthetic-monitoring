import json
from pathlib import Path

import pytest
from pydantic import ValidationError
from synmon_executor import runner
from synmon_executor.config import ExecutorConfig, describe


def test_defaults_without_environment():
    config = ExecutorConfig.from_env({"SYNMON_WORKER_ID": "w1"})
    assert config.worker_id == "w1"
    assert config.retries == 1 and config.timeout_s == 120.0
    assert config.run_budget_s is None and config.trace is False
    assert config.spool_dir == Path("/var/lib/synmon/spool")


def test_values_and_empty_variables():
    config = ExecutorConfig.from_env(
        {
            "SYNMON_WORKER_ID": "w1",
            "SYNMON_RETRIES": "0",
            "SYNMON_TIMEOUT_S": "30.5",
            "SYNMON_RUN_BUDGET_S": "",
            "SYNMON_TRACE": "1",
            "PATH": "/usr/bin",
        }
    )
    assert config.retries == 0 and config.timeout_s == 30.5
    assert config.run_budget_s is None and config.trace is True
    assert config.chromium_sandbox is False


def test_chromium_sandbox_flag():
    assert ExecutorConfig.from_env({"SYNMON_CHROMIUM_SANDBOX": "1"}).chromium_sandbox is True
    assert ExecutorConfig.from_env({"SYNMON_CHROMIUM_SANDBOX": "0"}).chromium_sandbox is False


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("SYNMON_RETRIES", "-1"),
        ("SYNMON_RETRIES", "one"),
        ("SYNMON_TIMEOUT_S", "0"),
        ("SYNMON_TIMEOUT_S", "inf"),
        ("SYNMON_RETRY_BACKOFF_S", "-0.5"),
        ("SYNMON_RUN_BUDGET_S", "0"),
        ("SYNMON_ARTIFACT_MAX_AGE_S", "7d"),
    ],
)
def test_invalid_values_name_the_variable(name, value):
    with pytest.raises(ValidationError) as info:
        ExecutorConfig.from_env({name: value})
    assert describe(info.value).startswith(f"{name}: ")


def test_invalid_config_still_writes_a_heartbeat(tmp_path, monkeypatch):
    hb_path = tmp_path / "heartbeat.json"
    monkeypatch.setenv("SYNMON_HEARTBEAT_PATH", str(hb_path))
    monkeypatch.setenv("SYNMON_WORKER_ID", "w1")
    monkeypatch.setenv("SYNMON_RETRIES", "-1")
    with pytest.raises(SystemExit) as info:
        runner.main()
    assert info.value.code == 2
    hb = json.loads(hb_path.read_text())
    assert hb["worker_id"] == "w1"
    assert hb["run_error"].startswith("invalid configuration: SYNMON_RETRIES")

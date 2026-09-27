import json
from pathlib import Path

import jsonschema
from synmon_contract.models import JourneyResult
from synmon_contract.schema_export import export, render

REPO = Path(__file__).resolve().parents[2]


def test_committed_schema_matches_models():
    expected = render()
    for name, text in expected.items():
        committed = (REPO / "schema" / name).read_text(encoding="utf-8")
        assert committed == text, f"{name} is stale; run `make schema`"


def test_sample_result_validates_against_committed_schema():
    schema = json.loads((REPO / "schema" / "synmon_result.schema.json").read_text("utf-8"))
    sample = JourneyResult(
        executor="playwright",
        executor_version="1.49.0",
        worker_id="w1",
        target_host="app.example.com",
        journey_name="login",
        journey_id="login",
        status=0,
        summary="ok",
        started_at=1000.0,
        duration_ms=5,
        max_age_s=900,
        interval_s=300,
    ).model_dump(mode="json")
    jsonschema.validate(sample, schema)


def test_export_writes_files(tmp_path):
    export(tmp_path)
    assert (tmp_path / "synmon_result.schema.json").exists()
    assert (tmp_path / "synmon_worker.schema.json").exists()

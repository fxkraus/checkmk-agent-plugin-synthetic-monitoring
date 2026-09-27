from synmon_executor.discovery import load_journeys
from synmon_executor.sdk import clear_registry, registered_journeys

JOURNEY_SRC = """
from synmon_executor import journey

@journey(name="probe", target_host="t.example.com", max_age_s=600, interval_s=300)
async def run(page, ctx):
    async with ctx.step("noop"):
        pass
"""


def test_load_journeys_registers_modules(tmp_path):
    clear_registry()
    (tmp_path / "probe.py").write_text(JOURNEY_SRC, encoding="utf-8")
    (tmp_path / "_ignored.py").write_text(
        "raise AssertionError('should be skipped')", encoding="utf-8"
    )

    loaded, errors = load_journeys(tmp_path)

    assert any(name.endswith("probe") for name in loaded)
    assert errors == []
    (jd,) = registered_journeys()
    assert jd.name == "probe" and jd.target_host == "t.example.com"


def test_broken_module_is_reported_and_does_not_block_others(tmp_path):
    clear_registry()
    (tmp_path / "a_broken.py").write_text("def oops(:\n", encoding="utf-8")
    (tmp_path / "b_probe.py").write_text(JOURNEY_SRC, encoding="utf-8")

    loaded, errors = load_journeys(tmp_path)

    assert [jd.name for jd in registered_journeys()] == ["probe"]
    assert len(loaded) == 1
    (err,) = errors
    assert err.startswith("a_broken.py: SyntaxError")

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


def test_journeys_registered_by_a_module_that_then_fails_are_dropped(tmp_path):
    clear_registry()
    (tmp_path / "half.py").write_text(
        JOURNEY_SRC + "\nraise RuntimeError('config missing')\n", encoding="utf-8"
    )

    loaded, errors = load_journeys(tmp_path)

    assert loaded == []
    assert errors == ["half.py: RuntimeError: config missing"]
    assert registered_journeys() == []


def _journey_src(name, host, journey_id=None):
    jid = f", journey_id={journey_id!r}" if journey_id else ""
    return (
        "from synmon_executor import journey\n\n"
        f"@journey(name={name!r}, target_host={host!r}, max_age_s=1, interval_s=1{jid})\n"
        "async def run(page, ctx):\n    pass\n"
    )


def test_invalid_target_host_is_a_load_error(tmp_path):
    clear_registry()
    (tmp_path / "evil.py").write_text(_journey_src("x", "a>>>>\n<<<<b"), encoding="utf-8")
    (tmp_path / "good.py").write_text(_journey_src("y", "ok.example.com"), encoding="utf-8")
    loaded, errors = load_journeys(tmp_path)
    assert loaded == ["synmon_journey_good"]
    assert len(errors) == 1 and errors[0].startswith("evil.py: invalid target_host")
    assert [j.name for j in registered_journeys()] == ["y"]


def test_colliding_spool_names_are_a_load_error(tmp_path):
    clear_registry()
    (tmp_path / "a.py").write_text(_journey_src("one", "a_b", "x"), encoding="utf-8")
    (tmp_path / "b.py").write_text(_journey_src("two", "a/b", "x"), encoding="utf-8")
    _, errors = load_journeys(tmp_path)
    assert len(errors) == 1 and errors[0].startswith("b.py:")
    assert [j.name for j in registered_journeys()] == ["one"]


def test_duplicate_journey_name_on_a_host_is_a_load_error(tmp_path):
    clear_registry()
    (tmp_path / "a.py").write_text(_journey_src("same", "h", "id1"), encoding="utf-8")
    (tmp_path / "b.py").write_text(_journey_src("same", "h", "id2"), encoding="utf-8")
    (tmp_path / "c.py").write_text(_journey_src("same", "other", "id1"), encoding="utf-8")
    _, errors = load_journeys(tmp_path)
    assert errors == ["b.py: duplicate journey name 'same' on h"]
    assert [(j.target_host, j.journey_id) for j in registered_journeys()] == [
        ("h", "id1"),
        ("other", "id1"),
    ]


def test_second_login_for_the_same_host_is_a_load_error(tmp_path):
    clear_registry()
    login_src = """
from synmon_executor import login

@login(target_host="app.example.com", name="{name}", max_age_s=600, interval_s=300)
async def run(page, ctx):
    pass
"""
    (tmp_path / "a.py").write_text(login_src.format(name="sso"), encoding="utf-8")
    (tmp_path / "b.py").write_text(login_src.format(name="form"), encoding="utf-8")

    _, errors = load_journeys(tmp_path)

    from synmon_executor.sdk import registered_logins

    assert [ld.name for ld in registered_logins()] == ["sso"]
    (err,) = errors
    assert "second login 'form' for app.example.com (already has 'sso')" in err


def test_invalid_decorator_arguments_are_load_errors(tmp_path):
    clear_registry()
    (tmp_path / "bad.py").write_text(
        JOURNEY_SRC.replace("interval_s=300", "interval_s=300, retries=-1"), encoding="utf-8"
    )

    _, errors = load_journeys(tmp_path)

    assert registered_journeys() == []
    (err,) = errors
    assert err.startswith("bad.py: ValueError: 'probe': retries must be >= 0")

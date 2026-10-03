import importlib.util
import io
import json
import os
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1] / "synmon_collector.py"


def _load():
    spec = importlib.util.spec_from_file_location("synmon_collector", PLUGIN)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _result(target, journey_id, **over):
    base = {
        "schema_version": "1.0.0",
        "executor": "playwright",
        "executor_version": "1.49.0",
        "worker_id": "w1",
        "target_host": target,
        "journey_name": journey_id,
        "journey_id": journey_id,
        "status": 0,
        "summary": "ok",
        "started_at": 1000.0,
        "duration_ms": 5,
        "max_age_s": 900,
        "interval_s": 300,
        "steps": [],
        "artifacts": {"screenshot_path": None, "trace_path": None},
        "error": None,
        "labels": {},
    }
    base.update(over)
    return base


def test_emits_worker_and_piggyback_sections(tmp_path):
    mod = _load()
    spool = tmp_path / "spool"
    spool.mkdir()
    (spool / "a__one.json").write_text(json.dumps(_result("a.example.com", "one")), "utf-8")
    (spool / "a__two.json").write_text(json.dumps(_result("a.example.com", "two")), "utf-8")
    (spool / "b__three.json").write_text(json.dumps(_result("b.example.com", "three")), "utf-8")
    (spool / "broken.json").write_text("{not json", "utf-8")
    hb = tmp_path / "heartbeat.json"
    hb.write_text(
        json.dumps(
            {
                "worker_id": "w1",
                "executor": "playwright",
                "heartbeat_at": 1000.0,
                "journeys_run": 3,
                "journeys_failed": 0,
            }
        ),
        "utf-8",
    )

    buf = io.StringIO()
    mod.main(spool_dir=spool, heartbeat_path=hb, out=buf)
    output = buf.getvalue()
    lines = output.splitlines()

    # Worker section first, with counts.
    assert lines[0] == "<<<synmon_worker:sep(0)>>>"
    worker = json.loads(lines[1])
    assert worker["results_found"] == 3 and worker["unparseable"] == 1
    assert worker["worker_id"] == "w1"

    # Piggyback blocks in sorted host order, journeys grouped per host.
    assert "<<<<a.example.com>>>>" in lines
    assert "<<<<b.example.com>>>>" in lines
    assert output.count("<<<synmon_journey:sep(0)>>>") == 2
    assert "<<<<>>>>" in lines
    a_idx = lines.index("<<<<a.example.com>>>>")
    assert lines[a_idx + 1] == "<<<synmon_journey:sep(0)>>>"
    assert json.loads(lines[a_idx + 2])["target_host"] == "a.example.com"

    # Assert sorted host order: a comes before b.
    assert lines.index("<<<<a.example.com>>>>") < lines.index("<<<<b.example.com>>>>")

    # Assert sorted journey order within host a: one before two.
    journey_one = json.loads(lines[a_idx + 2])
    journey_two = json.loads(lines[a_idx + 3])
    assert journey_one["journey_name"] == "one"
    assert journey_two["journey_name"] == "two"


def test_missing_spool_and_heartbeat_is_graceful(tmp_path):
    mod = _load()
    buf = io.StringIO()
    mod.main(spool_dir=tmp_path / "nope", heartbeat_path=tmp_path / "nohb.json", out=buf)
    lines = buf.getvalue().splitlines()
    assert lines[0] == "<<<synmon_worker:sep(0)>>>"
    worker = json.loads(lines[1])
    assert worker["results_found"] == 0 and worker["unparseable"] == 0
    # No piggyback sections when there are no results.
    assert "<<<synmon_journey:sep(0)>>>" not in buf.getvalue()


def test_passes_through_load_errors_and_skips(tmp_path):
    mod = _load()
    hb = tmp_path / "heartbeat.json"
    hb.write_text(
        json.dumps(
            {
                "heartbeat_at": 1000.0,
                "load_errors": ["x.py: SyntaxError: bad"],
                "journeys_skipped": 1,
            }
        ),
        "utf-8",
    )
    buf = io.StringIO()
    mod.main(spool_dir=tmp_path / "nope", heartbeat_path=hb, out=buf)
    worker = json.loads(buf.getvalue().splitlines()[1])
    assert worker["load_errors"] == ["x.py: SyntaxError: bad"]
    assert worker["journeys_skipped"] == 1


def test_rejects_hosts_that_could_forge_piggyback_headers(tmp_path):
    mod = _load()
    spool = tmp_path / "spool"
    spool.mkdir()
    forged = "x>>>>\n<<<<victim.example.com>>>>\n<<<local>>>"
    (spool / "forged.json").write_text(json.dumps(_result(forged, "one")), "utf-8")
    (spool / "list.json").write_text(json.dumps(_result(["a"], "two")), "utf-8")
    (spool / "int.json").write_text(json.dumps(_result(5, "three")), "utf-8")
    (spool / "empty.json").write_text(json.dumps(_result("", "four")), "utf-8")
    (spool / "name.json").write_text(json.dumps(_result("ok.example.com", "x", journey_name=1)))
    (spool / "good.json").write_text(json.dumps(_result("ok.example.com", "five")), "utf-8")

    buf = io.StringIO()
    mod.main(spool_dir=spool, heartbeat_path=tmp_path / "nohb.json", out=buf)
    output = buf.getvalue()

    assert "victim" not in output
    headers = [line for line in output.splitlines() if line.startswith("<<<<")]
    assert headers == ["<<<<ok.example.com>>>>", "<<<<>>>>"]
    worker = json.loads(output.splitlines()[1])
    assert worker["results_found"] == 1 and worker["unparseable"] == 5


def test_ignores_symlinks_fifos_and_oversized_files(tmp_path):
    mod = _load()
    spool = tmp_path / "spool"
    spool.mkdir()
    target = tmp_path / "elsewhere.json"
    target.write_text(json.dumps(_result("leak.example.com", "s")), "utf-8")
    (spool / "link.json").symlink_to(target)
    os.mkfifo(spool / "fifo.json")
    big = _result("big.example.com", "b", summary="x" * (mod.MAX_FILE_BYTES + 1))
    (spool / "big.json").write_text(json.dumps(big), "utf-8")
    (spool / "dir.json").mkdir()
    hb_target = tmp_path / "real_hb.json"
    hb_target.write_text(json.dumps({"heartbeat_at": 1.0}), "utf-8")
    hb = tmp_path / "heartbeat.json"
    hb.symlink_to(hb_target)

    buf = io.StringIO()
    mod.main(spool_dir=spool, heartbeat_path=hb, out=buf)
    lines = buf.getvalue().splitlines()

    worker = json.loads(lines[1])
    assert worker["results_found"] == 0 and worker["unparseable"] == 4
    assert "heartbeat_at" not in worker
    assert not any(line.startswith("<<<<") for line in lines)


def test_passes_through_run_error(tmp_path):
    mod = _load()
    hb = tmp_path / "heartbeat.json"
    hb.write_text(json.dumps({"heartbeat_at": 1.0, "run_error": "Error: no browser"}), "utf-8")
    buf = io.StringIO()
    mod.main(spool_dir=tmp_path / "nope", heartbeat_path=hb, out=buf)
    assert json.loads(buf.getvalue().splitlines()[1])["run_error"] == "Error: no browser"


def _spool_with(tmp_path, *hosts):
    spool = tmp_path / "spool"
    spool.mkdir()
    for i, host in enumerate(hosts):
        (spool / f"{i:03d}.json").write_text(json.dumps(_result(host, f"j{i}")), "utf-8")
    return spool


def _run(mod, tmp_path, spool, allowed_hosts_path):
    buf = io.StringIO()
    mod.main(
        spool_dir=spool,
        heartbeat_path=tmp_path / "nohb.json",
        out=buf,
        allowed_hosts_paths=[allowed_hosts_path]
        if isinstance(allowed_hosts_path, Path)
        else allowed_hosts_path,
    )
    lines = buf.getvalue().splitlines()
    headers = [line for line in lines if line.startswith("<<<<") and line != "<<<<>>>>"]
    return json.loads(lines[1]), headers


def test_allowlist_limits_piggyback_target_hosts(tmp_path):
    mod = _load()
    spool = _spool_with(tmp_path, "a.example.com", "victim.example.com", "b.example.com")
    allowed = tmp_path / "allowed_hosts"
    allowed.write_text("# hosts of segment 1\na.example.com\n\n  b.example.com  # web\n", "utf-8")

    worker, headers = _run(mod, tmp_path, spool, allowed)

    assert headers == ["<<<<a.example.com>>>>", "<<<<b.example.com>>>>"]
    assert worker["allowlist"] is True
    assert worker["not_allowed"] == 1 and worker["results_found"] == 2


def test_without_allowlist_every_valid_host_passes_and_is_flagged(tmp_path):
    mod = _load()
    spool = _spool_with(tmp_path, "a.example.com")

    worker, headers = _run(mod, tmp_path, spool, tmp_path / "missing")

    assert headers == ["<<<<a.example.com>>>>"]
    assert worker["allowlist"] is False and worker["not_allowed"] == 0


def test_unreadable_allowlist_fails_closed(tmp_path):
    mod = _load()
    spool = _spool_with(tmp_path, "a.example.com")
    real = tmp_path / "real_allowed"
    real.write_text("a.example.com\n", "utf-8")
    link = tmp_path / "allowed_hosts"
    link.symlink_to(real)

    worker, headers = _run(mod, tmp_path, spool, link)

    assert headers == []
    assert worker["allowlist"] is True and worker["not_allowed"] == 1


def test_symlinked_spool_directory_is_not_followed(tmp_path):
    mod = _load()
    elsewhere = _spool_with(tmp_path, "a.example.com")
    spool = tmp_path / "spool_link"
    spool.symlink_to(elsewhere, target_is_directory=True)

    worker, headers = _run(mod, tmp_path, spool, tmp_path / "missing")

    assert headers == []
    assert worker["results_found"] == 0 and worker["unparseable"] == 1


def test_file_count_limit(tmp_path, monkeypatch):
    mod = _load()
    monkeypatch.setattr(mod, "MAX_FILES", 2)
    spool = _spool_with(
        tmp_path, "a.example.com", "b.example.com", "c.example.com", "d.example.com"
    )

    worker, headers = _run(mod, tmp_path, spool, tmp_path / "missing")

    assert headers == ["<<<<a.example.com>>>>", "<<<<b.example.com>>>>"]
    assert worker["overflow"] == 2


def test_total_size_limit(tmp_path, monkeypatch):
    mod = _load()
    spool = _spool_with(tmp_path, "a.example.com", "b.example.com", "c.example.com")
    one_file = (spool / "000.json").stat().st_size
    monkeypatch.setattr(mod, "MAX_TOTAL_BYTES", one_file + 1)

    worker, headers = _run(mod, tmp_path, spool, tmp_path / "missing")

    assert len(headers) == 2
    assert worker["overflow"] == 1


def test_bakery_allowlist_takes_precedence_over_install_sh(tmp_path):
    mod = _load()
    spool = _spool_with(tmp_path, "a.example.com", "b.example.com")
    baked = tmp_path / "synmon_allowed_hosts"
    baked.write_text("# Created by Check_MK Agent Bakery.\nb.example.com\n", "utf-8")
    installed = tmp_path / "allowed_hosts"
    installed.write_text("a.example.com\n", "utf-8")

    worker, headers = _run(mod, tmp_path, spool, [baked, installed])
    assert headers == ["<<<<b.example.com>>>>"] and worker["not_allowed"] == 1

    worker, headers = _run(mod, tmp_path, spool, [tmp_path / "absent", installed])
    assert headers == ["<<<<a.example.com>>>>"] and worker["allowlist"] is True


def test_default_allowlist_locations_follow_the_agent_config_dir(monkeypatch):
    monkeypatch.delenv("SYNMON_ALLOWED_HOSTS", raising=False)
    monkeypatch.setenv("MK_CONFDIR", "/etc/agent-conf")
    assert _load().ALLOWED_HOSTS_PATHS == [
        Path("/etc/agent-conf/synmon_allowed_hosts"),
        Path("/etc/synmon/allowed_hosts"),
    ]
    monkeypatch.setenv("SYNMON_ALLOWED_HOSTS", "/custom")
    assert _load().ALLOWED_HOSTS_PATHS == [Path("/custom")]

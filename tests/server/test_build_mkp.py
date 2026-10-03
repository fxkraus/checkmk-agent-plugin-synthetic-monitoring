"""Verify scripts/build_mkp.py produces a structurally valid .mkp (no Checkmk site needed)."""

import ast
import importlib.util
import io
import json
import tarfile
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_STAGE_DIR = _REPO_ROOT / "checkmk_mkp"


def _load_builder():
    spec = importlib.util.spec_from_file_location(
        "synmon_build_mkp", _REPO_ROOT / "scripts" / "build_mkp.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _manifest_version() -> str:
    return json.loads((_STAGE_DIR / "manifest.json").read_text())["version"]


def test_mkp_filename_and_outer_members():
    builder = _load_builder()
    filename, data = builder.build_mkp_bytes(_STAGE_DIR)
    # The release job bumps the manifest version, so never hard-code it here.
    assert filename == f"synmon-{_manifest_version()}.mkp"
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
        names = set(tar.getnames())
    assert {"info", "info.json", "cmk_addons_plugins.tar", "agents.tar", "lib.tar"} <= names


def test_info_roundtrips_like_checkmk_reads_it():
    builder = _load_builder()
    _, data = builder.build_mkp_bytes(_STAGE_DIR)
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
        raw_info = tar.extractfile("info").read().decode()
        raw_json = tar.extractfile("info.json").read().decode()
    # Checkmk parses `info` with ast.literal_eval; it must be a valid Python literal.
    info = ast.literal_eval(raw_info)
    assert info["name"] == "synmon"
    assert info["version"] == _manifest_version()
    assert info["version.min_required"] == "2.4.0p32"
    assert len(info["files"]["cmk_addons_plugins"]) == 10
    assert info["files"]["agents"] == ["plugins/synmon_collector.py"]
    # info.json carries the same manifest.
    assert json.loads(raw_json)["name"] == "synmon"


def test_inner_tar_members_are_site_relative_paths():
    builder = _load_builder()
    _, data = builder.build_mkp_bytes(_STAGE_DIR)
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
        inner = tar.extractfile("cmk_addons_plugins.tar").read()
    with tarfile.open(fileobj=io.BytesIO(inner), mode="r") as part:
        members = set(part.getnames())
    assert "synmon/lib/parsing.py" in members
    assert "synmon/agent_based/synmon_journey.py" in members
    assert "synmon/rulesets/synmon_worker.py" in members
    assert "synmon/checkman/synmon_journey" in members
    assert len(members) == 10


def test_lib_part_carries_the_v1_bakery_plugin():
    # Bakery API v1 plug-ins are only loaded from cmk.base.cee.plugins.bakery (2.4 and 2.5),
    # i.e. local/lib/python3/cmk/base/cee/plugins/bakery — not from cmk_addons/plugins.
    builder = _load_builder()
    _, data = builder.build_mkp_bytes(_STAGE_DIR)
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
        inner = tar.extractfile("lib.tar").read()
    with tarfile.open(fileobj=io.BytesIO(inner), mode="r") as part:
        assert part.getnames() == ["python3/cmk/base/cee/plugins/bakery/synmon.py"]


def test_agents_part_carries_the_collector():
    builder = _load_builder()
    _, data = builder.build_mkp_bytes(_STAGE_DIR)
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
        inner = tar.extractfile("agents.tar").read()
    with tarfile.open(fileobj=io.BytesIO(inner), mode="r") as part:
        assert part.getnames() == ["plugins/synmon_collector.py"]


def test_staged_agent_plugin_matches_authoritative_source():
    # The baked copy under the MKP agents/ part must stay byte-identical to agent_plugin/.
    staged = (_STAGE_DIR / "agents" / "plugins" / "synmon_collector.py").read_bytes()
    source = (_REPO_ROOT / "agent_plugin" / "synmon_collector.py").read_bytes()
    assert staged == source


def _staged_copy(tmp_path: Path) -> Path:
    stage = tmp_path / "stage"
    stage.mkdir()
    (stage / "manifest.json").write_text((_STAGE_DIR / "manifest.json").read_text())
    return stage


def test_set_version_rewrites_only_the_version_line(tmp_path):
    builder = _load_builder()
    stage = _staged_copy(tmp_path)
    before = (stage / "manifest.json").read_text()

    builder.set_manifest_version(stage, "9.8.7")

    after = (stage / "manifest.json").read_text()
    changed = [
        (a, b) for a, b in zip(before.splitlines(), after.splitlines(), strict=True) if a != b
    ]
    assert len(changed) == 1 and changed[0][1].strip() == '"version": "9.8.7",'
    manifest = json.loads(after)
    assert manifest["version"] == "9.8.7"
    assert manifest["version.min_required"] == json.loads(before)["version.min_required"]


def test_set_version_rejects_non_semver(tmp_path):
    import pytest

    builder = _load_builder()
    stage = _staged_copy(tmp_path)
    for bad in ("1.2", "v1.2.3", "1.2.3-rc1", '1.2.3", "x'):
        with pytest.raises(ValueError):
            builder.set_manifest_version(stage, bad)

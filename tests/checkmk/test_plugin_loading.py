"""Load the MKP with Checkmk's own plug-in loaders (runs only inside a Checkmk image).

The offline suite tests the stdlib `lib/`; this proves Checkmk actually *finds* every plug-in in
the directories the MKP installs them to, on each supported Checkmk version.
"""

import inspect
import json
from pathlib import Path

import cmk.base.api.bakery.register as bakery_register
from cmk.agent_based import v2 as agent_based_v2
from cmk.discover_plugins import PluginGroup, discover_all_plugins
from cmk.graphing import v1 as graphing_v1
from cmk.mkp_tool import PackagePart
from cmk.rulesets import v1 as rulesets_v1


def _discovered(group: PluginGroup, prefixes) -> set[str]:
    kwargs = {"raise_errors": True}
    # Checkmk 2.5 made this keyword mandatory; 2.4 does not know it.
    if "skip_wrong_types" in inspect.signature(discover_all_plugins).parameters:
        kwargs["skip_wrong_types"] = False
    collection = discover_all_plugins(group, prefixes, **kwargs)
    return {
        location.name
        for location in collection.plugins
        if location.module.startswith("cmk_addons.plugins.synmon.")
    }


def test_agent_based_plugins_are_discovered():
    names = _discovered(PluginGroup.AGENT_BASED, agent_based_v2.entry_point_prefixes())
    assert {
        "agent_section_synmon_journey",
        "check_plugin_synmon_journey",
        "agent_section_synmon_worker",
        "check_plugin_synmon_worker",
    } <= names


def test_rulesets_are_discovered():
    names = _discovered(PluginGroup.RULESETS, rulesets_v1.entry_point_prefixes())
    assert {
        "rule_spec_synmon_journey",
        "rule_spec_synmon_worker",
        "rule_spec_synmon_bakery",
    } <= names


def test_graphing_is_discovered():
    names = _discovered(PluginGroup.GRAPHING, graphing_v1.entry_point_prefixes())
    assert {"metric_synmon_duration", "graph_synmon_steps", "perfometer_synmon_lcp"} <= names


def test_bakery_plugin_is_registered_by_the_agent_bakery():
    assert "synmon" in {str(name) for name in bakery_register.get_bakery_plugins()}


def test_manifest_parts_are_known_to_checkmk():
    manifest = Path(__file__).resolve().parents[2] / "checkmk_mkp" / "manifest.json"
    for part in json.loads(manifest.read_text())["files"]:
        PackagePart(part)  # raises ValueError for a part Checkmk would not install


def test_worker_check_alerts_on_a_stale_heartbeat_without_any_rule():
    from cmk_addons.plugins.synmon.agent_based import synmon_worker

    params = synmon_worker.check_plugin_synmon_worker.check_default_parameters
    assert params == {"heartbeat_age_levels": ("fixed", (600.0, 1800.0))}


def test_declared_step_metrics_match_what_the_check_emits():
    from cmk_addons.plugins.synmon.graphing import synmon as graphing
    from cmk_addons.plugins.synmon.lib import evaluate

    assert len(graphing._STEP_NAMES) == evaluate.MAX_STEP_METRICS


def test_bakery_deploys_the_allowlist_into_the_agent_config_dir():
    from cmk.base.cee.plugins.bakery import synmon as bakery
    from cmk.base.plugins.bakery.bakery_api.v1 import Plugin, PluginConfig

    files = list(bakery._get_synmon_files({"allowed_hosts": ["a.example.com", "b"]}))
    assert [type(f) for f in files] == [Plugin, PluginConfig]
    config = files[1]
    assert list(config.lines) == ["a.example.com", "b"]
    assert str(config.target) == "synmon_allowed_hosts" and config.include_header
    # Without the setting no file is deployed (install.sh's /etc/synmon/allowed_hosts applies).
    assert [type(f) for f in bakery._get_synmon_files({})] == [Plugin]


def test_bakery_ruleset_form_builds():
    from cmk_addons.plugins.synmon.rulesets import synmon_bakery

    form = synmon_bakery.rule_spec_synmon_bakery.parameter_form()
    assert set(form.elements) == {"interval", "allowed_hosts"}

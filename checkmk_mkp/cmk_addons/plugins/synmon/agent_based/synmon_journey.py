"""Checkmk check plugin: one service per synthetic-monitoring journey."""

import time
from collections.abc import Mapping

from cmk.agent_based.v2 import (
    AgentSection,
    CheckPlugin,
    CheckResult,
    DiscoveryResult,
    Metric,
    Result,
    Service,
    State,
    StringTable,
)
from cmk_addons.plugins.synmon.lib import evaluate, parsing


def parse_synmon_journey(string_table: StringTable) -> dict[str, dict]:
    return {j["journey_name"]: j for j in parsing.parse_journey_section(string_table)}


agent_section_synmon_journey = AgentSection(
    name="synmon_journey",
    parse_function=parse_synmon_journey,
)


def discover_synmon_journey(section: dict[str, dict]) -> DiscoveryResult:
    for journey_name in section:
        yield Service(item=journey_name)


def check_synmon_journey(item: str, params: Mapping, section: dict[str, dict]) -> CheckResult:
    journey = section.get(item)
    if journey is None:
        return
    outcome = evaluate.evaluate_journey(journey, params, time.time())
    result_kwargs: dict = {"state": State(outcome.state), "summary": outcome.summary}
    if outcome.details:
        result_kwargs["details"] = "\n".join(outcome.details)
    yield Result(**result_kwargs)
    for metric in outcome.metrics:
        yield Metric(metric.name, metric.value, levels=metric.levels)


check_plugin_synmon_journey = CheckPlugin(
    name="synmon_journey",
    service_name="Journey %s",
    discovery_function=discover_synmon_journey,
    check_function=check_synmon_journey,
    check_ruleset_name="synmon_journey",
    check_default_parameters={},
)

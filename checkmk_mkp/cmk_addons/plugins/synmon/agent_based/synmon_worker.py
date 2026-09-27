"""Checkmk check plugin: synthetic-monitoring worker scheduler health (one service per worker)."""

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


def parse_synmon_worker(string_table: StringTable) -> dict | None:
    return parsing.parse_worker_section(string_table)


agent_section_synmon_worker = AgentSection(
    name="synmon_worker",
    parse_function=parse_synmon_worker,
)


def discover_synmon_worker(section: dict | None) -> DiscoveryResult:
    if section is not None:
        yield Service()


def check_synmon_worker(params: Mapping, section: dict | None) -> CheckResult:
    if section is None:
        return
    outcome = evaluate.evaluate_worker(section, params, time.time())
    result_kwargs: dict = {"state": State(outcome.state), "summary": outcome.summary}
    if outcome.details:
        result_kwargs["details"] = "\n".join(outcome.details)
    yield Result(**result_kwargs)
    for metric in outcome.metrics:
        yield Metric(metric.name, metric.value, levels=metric.levels)


check_plugin_synmon_worker = CheckPlugin(
    name="synmon_worker",
    service_name="Synthetic Worker Scheduler",
    discovery_function=discover_synmon_worker,
    check_function=check_synmon_worker,
    check_ruleset_name="synmon_worker",
    check_default_parameters={},
)

"""Agent Bakery ruleset: deploy the synmon agent plugin to worker hosts."""

from cmk.rulesets.v1 import Help, Title
from cmk.rulesets.v1.form_specs import (
    DictElement,
    Dictionary,
    TimeMagnitude,
    TimeSpan,
)
from cmk.rulesets.v1.rule_specs import AgentConfig, Topic


def _form_synmon_bakery() -> Dictionary:
    return Dictionary(
        elements={
            "interval": DictElement(
                parameter_form=TimeSpan(
                    title=Title("Agent plugin cache interval"),
                    help_text=Help(
                        "Run the collector as a cached (asynchronous) agent plugin at this "
                        "interval. Omit to run it on every agent poll — the collector only reads "
                        "the spool, so this is cheap."
                    ),
                    displayed_magnitudes=[TimeMagnitude.SECOND, TimeMagnitude.MINUTE],
                ),
            ),
        },
        help_text=Help(
            "Deploy the synthetic-monitoring agent plugin (synmon_collector) to matching worker "
            "hosts. The plugin reads the executor's spool and emits the synmon_journey / "
            "synmon_worker sections."
        ),
    )


rule_spec_synmon_bakery = AgentConfig(
    name="synmon",
    title=Title("Synthetic monitoring: agent deployment"),
    topic=Topic.SYNTHETIC_MONITORING,
    parameter_form=_form_synmon_bakery,
)

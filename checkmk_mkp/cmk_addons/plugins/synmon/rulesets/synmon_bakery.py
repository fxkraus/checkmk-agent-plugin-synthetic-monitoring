"""Agent Bakery ruleset: deploy the synmon agent plugin to worker hosts."""

from cmk.rulesets.v1 import Help, Label, Message, Title
from cmk.rulesets.v1.form_specs import (
    DictElement,
    Dictionary,
    List,
    String,
    TimeMagnitude,
    TimeSpan,
    validators,
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
            "allowed_hosts": DictElement(
                parameter_form=List(
                    title=Title("Allowed target hosts"),
                    help_text=Help(
                        "The only Checkmk hosts this worker may send journey results to (as "
                        "piggyback data). Results for other hosts are dropped and counted on the "
                        "worker service. Deployed to /etc/check_mk/synmon_allowed_hosts, which "
                        "takes precedence over /etc/synmon/allowed_hosts. An empty list forwards "
                        "nothing. Without this setting and without /etc/synmon/allowed_hosts, "
                        "every host is accepted and the worker service is WARN."
                    ),
                    element_template=String(
                        custom_validate=(
                            validators.MatchRegex(
                                regex=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,252}$",
                                error_msg=Message("Enter a Checkmk host name."),
                            ),
                        ),
                    ),
                    add_element_label=Label("Add host"),
                    editable_order=False,
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

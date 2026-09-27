"""WATO check parameters for the synthetic-monitoring worker scheduler health."""

from cmk.rulesets.v1 import Help, Title
from cmk.rulesets.v1.form_specs import (
    DefaultValue,
    DictElement,
    Dictionary,
    LevelDirection,
    SimpleLevels,
    TimeMagnitude,
    TimeSpan,
)
from cmk.rulesets.v1.rule_specs import CheckParameters, HostCondition, Topic


def _form_synmon_worker() -> Dictionary:
    return Dictionary(
        elements={
            "heartbeat_age_levels": DictElement(
                parameter_form=SimpleLevels(
                    title=Title("Scheduler heartbeat age (upper levels)"),
                    level_direction=LevelDirection.UPPER,
                    form_spec_template=TimeSpan(
                        displayed_magnitudes=[
                            TimeMagnitude.SECOND,
                            TimeMagnitude.MINUTE,
                            TimeMagnitude.HOUR,
                        ]
                    ),
                    prefill_fixed_levels=DefaultValue((600.0, 1800.0)),
                ),
            ),
        },
        help_text=Help(
            "Alert when the worker's executor heartbeat is too old (scheduler stalled)."
        ),
    )


rule_spec_synmon_worker = CheckParameters(
    name="synmon_worker",
    title=Title("Synthetic monitoring: worker scheduler"),
    topic=Topic.SYNTHETIC_MONITORING,
    parameter_form=_form_synmon_worker,
    condition=HostCondition(),
)

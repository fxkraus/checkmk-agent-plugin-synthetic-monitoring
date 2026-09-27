"""WATO check parameters for synthetic-monitoring journeys."""

from cmk.rulesets.v1 import Help, Title
from cmk.rulesets.v1.form_specs import (
    DefaultValue,
    DictElement,
    Dictionary,
    Float,
    Integer,
    LevelDirection,
    ServiceState,
    SimpleLevels,
    TimeMagnitude,
    TimeSpan,
)
from cmk.rulesets.v1.rule_specs import CheckParameters, HostAndItemCondition, Topic

_DURATION_MAGNITUDES = [TimeMagnitude.SECOND, TimeMagnitude.MINUTE, TimeMagnitude.HOUR]


def _form_synmon_journey() -> Dictionary:
    return Dictionary(
        elements={
            "cls_levels": DictElement(
                parameter_form=SimpleLevels(
                    title=Title("Cumulative Layout Shift (upper levels)"),
                    level_direction=LevelDirection.UPPER,
                    form_spec_template=Float(),
                    prefill_fixed_levels=DefaultValue((0.1, 0.25)),
                ),
            ),
            "inp_levels": DictElement(
                parameter_form=SimpleLevels(
                    title=Title("Interaction to Next Paint (upper levels)"),
                    level_direction=LevelDirection.UPPER,
                    form_spec_template=TimeSpan(displayed_magnitudes=_DURATION_MAGNITUDES),
                    prefill_fixed_levels=DefaultValue((0.2, 0.5)),
                ),
            ),
            "lcp_levels": DictElement(
                parameter_form=SimpleLevels(
                    title=Title("Largest Contentful Paint (upper levels)"),
                    level_direction=LevelDirection.UPPER,
                    form_spec_template=TimeSpan(displayed_magnitudes=_DURATION_MAGNITUDES),
                    prefill_fixed_levels=DefaultValue((2.5, 4.0)),
                ),
            ),
            "staleness_grace_s": DictElement(
                parameter_form=Integer(
                    title=Title("Staleness grace beyond max_age (seconds)"),
                    prefill=DefaultValue(0),
                ),
            ),
            "retried_state": DictElement(
                parameter_form=ServiceState(
                    title=Title("State when the journey succeeded only after a retry"),
                    help_text=Help(
                        "A pass that needed retries still hit a failure. WARN keeps it visible "
                        "in availability/SLA reports; choose OK to ignore transient failures."
                    ),
                    prefill=DefaultValue(ServiceState.WARN),
                ),
            ),
            "staleness_state": DictElement(
                parameter_form=ServiceState(
                    title=Title("State when the result is stale"),
                    help_text=Help(
                        "Replaces the outdated result's state. UNKNOWN (default) means "
                        "'no current measurement', which availability/SLA reports can exclude "
                        "instead of counting it as an application outage."
                    ),
                    prefill=DefaultValue(ServiceState.UNKNOWN),
                ),
            ),
            "step_duration_levels": DictElement(
                parameter_form=SimpleLevels(
                    title=Title("Per-step duration (upper levels)"),
                    level_direction=LevelDirection.UPPER,
                    form_spec_template=TimeSpan(displayed_magnitudes=_DURATION_MAGNITUDES),
                    prefill_fixed_levels=DefaultValue((5.0, 15.0)),
                ),
            ),
            "total_duration_levels": DictElement(
                parameter_form=SimpleLevels(
                    title=Title("Total journey duration (upper levels)"),
                    level_direction=LevelDirection.UPPER,
                    form_spec_template=TimeSpan(displayed_magnitudes=_DURATION_MAGNITUDES),
                    prefill_fixed_levels=DefaultValue((10.0, 30.0)),
                ),
            ),
        },
        help_text=Help("Thresholds and staleness handling for one synthetic-monitoring journey."),
    )


rule_spec_synmon_journey = CheckParameters(
    name="synmon_journey",
    title=Title("Synthetic monitoring: journey"),
    topic=Topic.SYNTHETIC_MONITORING,
    parameter_form=_form_synmon_journey,
    condition=HostAndItemCondition(item_title=Title("Journey name")),
)

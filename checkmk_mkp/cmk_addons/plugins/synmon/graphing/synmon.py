"""Metrics, perfometer, and graphs for synthetic-monitoring durations."""

from cmk.graphing.v1 import Title
from cmk.graphing.v1.graphs import Graph, MinimalRange
from cmk.graphing.v1.metrics import AutoPrecision, Color, DecimalNotation, Metric, Unit
from cmk.graphing.v1.perfometers import FocusRange, Open, Perfometer

UNIT_SECONDS = Unit(DecimalNotation("s"), AutoPrecision(2))

metric_synmon_duration = Metric(
    name="synmon_duration",
    title=Title("Journey duration"),
    unit=UNIT_SECONDS,
    color=Color.BLUE,
)

metric_synmon_age = Metric(
    name="synmon_age",
    title=Title("Result age"),
    unit=UNIT_SECONDS,
    color=Color.GRAY,
)

metric_synmon_heartbeat_age = Metric(
    name="synmon_heartbeat_age",
    title=Title("Scheduler heartbeat age"),
    unit=UNIT_SECONDS,
    color=Color.GRAY,
)

_STEP_COLORS = [
    Color.LIGHT_BLUE,
    Color.LIGHT_GREEN,
    Color.LIGHT_CYAN,
    Color.LIGHT_PURPLE,
    Color.ORANGE,
    Color.LIGHT_YELLOW,
    Color.LIGHT_PINK,
    Color.LIGHT_BROWN,
]
# Keep in sync with evaluate.MAX_STEP_METRICS (the check emits no step metric beyond it). A step
# metric is identified by its position: inserting a step shifts the history of all later ones.
_STEP_NAMES = [f"synmon_step_{i}_duration" for i in range(1, 9)]

# Declare per-step metrics; bind each to a module global so the loader registers it.
for _i, (_name, _color) in enumerate(zip(_STEP_NAMES, _STEP_COLORS, strict=True), start=1):
    globals()[f"metric_synmon_step_{_i}_duration"] = Metric(
        name=_name,
        title=Title(f"Step {_i} duration"),
        unit=UNIT_SECONDS,
        color=_color,
    )

perfometer_synmon_duration = Perfometer(
    name="synmon_duration",
    focus_range=FocusRange(Open(0), Open(30)),
    segments=["synmon_duration"],
)

graph_synmon_duration = Graph(
    name="synmon_duration",
    title=Title("Journey total duration"),
    minimal_range=MinimalRange(0, 10),
    simple_lines=["synmon_duration"],
)

# Every step metric is optional: a journey rarely has all eight, and the graph must still render.
graph_synmon_steps = Graph(
    name="synmon_steps",
    title=Title("Journey step durations"),
    compound_lines=_STEP_NAMES,
    optional=_STEP_NAMES,
)

UNIT_COUNT = Unit(DecimalNotation(""), AutoPrecision(3))

metric_synmon_lcp = Metric(
    name="synmon_lcp",
    title=Title("Largest Contentful Paint"),
    unit=UNIT_SECONDS,
    color=Color.PURPLE,
)

metric_synmon_inp = Metric(
    name="synmon_inp",
    title=Title("Interaction to Next Paint"),
    unit=UNIT_SECONDS,
    color=Color.RED,
)

metric_synmon_fcp = Metric(
    name="synmon_fcp",
    title=Title("First Contentful Paint"),
    unit=UNIT_SECONDS,
    color=Color.LIGHT_BLUE,
)

metric_synmon_ttfb = Metric(
    name="synmon_ttfb",
    title=Title("Time to First Byte"),
    unit=UNIT_SECONDS,
    color=Color.CYAN,
)

metric_synmon_cls = Metric(
    name="synmon_cls",
    title=Title("Cumulative Layout Shift"),
    unit=UNIT_COUNT,
    color=Color.ORANGE,
)

perfometer_synmon_lcp = Perfometer(
    name="synmon_lcp", focus_range=FocusRange(Open(0), Open(5)), segments=["synmon_lcp"]
)

graph_synmon_web_vitals = Graph(
    name="synmon_web_vitals",
    title=Title("Core Web Vitals (timings)"),
    simple_lines=["synmon_lcp", "synmon_inp", "synmon_fcp", "synmon_ttfb"],
    optional=["synmon_lcp", "synmon_inp", "synmon_fcp", "synmon_ttfb"],
)

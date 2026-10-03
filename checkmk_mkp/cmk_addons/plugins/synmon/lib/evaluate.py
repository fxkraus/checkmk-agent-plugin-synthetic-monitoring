"""Pure status/staleness/threshold evaluation for synmon. Standard library only."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field

OK = 0
WARN = 1
CRIT = 2
UNKNOWN = 3

_STATE_NAME = {OK: "OK", WARN: "WARN", CRIT: "CRIT", UNKNOWN: "UNKNOWN"}

Levels = tuple[float, float] | None

# Must match the step metrics declared in graphing/synmon.py.
MAX_STEP_METRICS = 8
# A result timestamp further in the future than this means the worker's clock is ahead.
CLOCK_SKEW_TOLERANCE_S = 60.0


def norm_levels(value: object) -> Levels:
    """Normalize a WATO SimpleLevels/Levels value into a plain ``(warn, crit)`` tuple or ``None``.

    Checkmk's ``SimpleLevels`` form spec yields ``("no_levels", None)`` or
    ``("fixed", (warn, crit))`` (and ``("cmk_postprocessed", "predictive_levels", ...)`` for
    predictive levels, which we do not support as static thresholds). A bare ``(warn, crit)`` tuple
    is also accepted so the pure unit tests can pass thresholds directly.
    """
    if value is None:
        return None
    if isinstance(value, tuple) and len(value) == 2 and isinstance(value[0], str):
        kind, payload = value
        if kind == "fixed" and isinstance(payload, (tuple, list)) and len(payload) == 2:
            return (float(payload[0]), float(payload[1]))
        return None  # no_levels / predictive -> no static thresholds
    if isinstance(value, (tuple, list)) and len(value) == 2:
        return (float(value[0]), float(value[1]))
    return None


def level_state(value: float, levels: Levels) -> int:
    """Upper warn/crit levels -> state."""
    if levels is None:
        return OK
    warn, crit = levels
    if value >= crit:
        return CRIT
    if value >= warn:
        return WARN
    return OK


@dataclass
class MetricSpec:
    name: str
    value: float
    levels: Levels = None


@dataclass
class StepView:
    name: str
    state: int
    duration_s: float
    message: str | None


@dataclass
class JourneyOutcome:
    state: int
    summary: str
    details: list[str] = field(default_factory=list)
    metrics: list[MetricSpec] = field(default_factory=list)
    steps: list[StepView] = field(default_factory=list)


def _f(value: object, default: float = 0.0) -> float:
    """A finite float, or ``default`` (NaN/inf would disable every comparison)."""
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def _timestamp(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if math.isfinite(value) else None


def _state(value: object) -> int:
    """A reported status, or UNKNOWN if it is not one of the four states."""
    if isinstance(value, int) and not isinstance(value, bool) and OK <= value <= UNKNOWN:
        return value
    return UNKNOWN


def _dict(value: object) -> dict:
    return value if isinstance(value, dict) else {}


def evaluate_journey(journey: dict, params: Mapping, now: float) -> JourneyOutcome:
    state = _state(journey.get("status", UNKNOWN))
    details: list[str] = []
    if state == UNKNOWN and journey.get("status", UNKNOWN) != UNKNOWN:
        details.append(f"Invalid status reported: {journey.get('status')!r}")
    metrics: list[MetricSpec] = []
    steps: list[StepView] = []

    duration_s = _f(journey.get("duration_ms")) / 1000.0
    total_levels = norm_levels(params.get("total_duration_levels"))
    metrics.append(MetricSpec("synmon_duration", duration_s, total_levels))
    state = max(state, level_state(duration_s, total_levels))

    stale_note: str | None = None
    started_at = _timestamp(journey.get("started_at"))
    max_age = _f(journey.get("max_age_s"))
    grace = _f(params.get("staleness_grace_s"))
    if started_at is None:
        # Without a valid timestamp the result's age is unknown: never treat it as current.
        stale_note = "Stale result (no valid started_at timestamp)"
        details.append(stale_note)
    else:
        age = now - started_at
        metrics.append(MetricSpec("synmon_age", age))
        if age < -CLOCK_SKEW_TOLERANCE_S:
            state = max(state, WARN)
            details.append(
                f"Result timestamp is {int(-age)}s in the future: "
                "the worker clock is ahead of the Checkmk server (check NTP)"
            )
        # abs(): a timestamp far in the future must not keep a result fresh forever.
        if abs(age) > max_age + grace:
            stale_note = (
                f"Stale result ({int(age)}s old, max_age {int(max_age)}s + grace {int(grace)}s)"
            )
            details.append(stale_note)

    duplicates = journey.get("duplicate_workers")
    if isinstance(duplicates, list) and duplicates:
        state = max(state, WARN)
        details.append(
            "Journey reported by several workers: "
            + ", ".join(str(w) for w in duplicates)
            + " (showing the newest result)"
        )

    step_levels = norm_levels(params.get("step_duration_levels"))
    raw_steps = journey.get("steps")
    for i, raw in enumerate(raw_steps if isinstance(raw_steps, list) else [], start=1):
        if not isinstance(raw, dict):
            continue
        sdur = _f(raw.get("duration_ms")) / 1000.0
        sstate = _state(raw.get("status", UNKNOWN))
        sstate = max(sstate, level_state(sdur, step_levels))
        name = raw.get("name") or f"step{i}"
        message = raw.get("message")
        steps.append(StepView(name, sstate, sdur, message))
        if i <= MAX_STEP_METRICS:
            metrics.append(MetricSpec(f"synmon_step_{i}_duration", sdur, step_levels))
        state = max(state, sstate)
        line = f"Step {i} {name}: {_STATE_NAME.get(sstate, sstate)} ({sdur:.2f}s)"
        if message:
            line += f" — {message}"
        details.append(line)

    error = _dict(journey.get("error"))
    if error:
        details.append(
            f"Error: {error.get('type')} at step '{error.get('step')}': {error.get('message')}"
        )

    artifacts = _dict(journey.get("artifacts"))
    if artifacts.get("screenshot_path"):
        details.append(f"Screenshot: {artifacts['screenshot_path']}")
    if artifacts.get("trace_path"):
        details.append(f"Trace: {artifacts['trace_path']}")

    vitals = _dict(journey.get("vitals"))
    # (contract_field, metric_name, param_key, scale)  scale converts ms -> the metric unit
    _VITALS = [
        ("lcp_ms", "synmon_lcp", "lcp_levels", 0.001),
        ("inp_ms", "synmon_inp", "inp_levels", 0.001),
        ("fcp_ms", "synmon_fcp", None, 0.001),
        ("ttfb_ms", "synmon_ttfb", None, 0.001),
        ("cls", "synmon_cls", "cls_levels", 1.0),
    ]
    shown = []
    for field_name, metric_name, param_key, scale in _VITALS:
        raw = vitals.get(field_name)
        if raw is None:
            continue
        value = _f(raw) * scale
        levels = norm_levels(params.get(param_key)) if param_key else None
        metrics.append(MetricSpec(metric_name, value, levels))
        state = max(state, level_state(value, levels))
        shown.append(f"{metric_name.removeprefix('synmon_').upper()}={value:g}")
    if shown:
        details.append("Web Vitals: " + " ".join(shown))

    if len(steps) > MAX_STEP_METRICS:
        details.append(
            f"Step duration metrics are recorded for the first {MAX_STEP_METRICS} steps only"
        )

    attempts = int(_f(journey.get("attempts", 1), 1.0))
    metrics.append(MetricSpec("synmon_attempts", float(attempts)))
    if attempts > 1:
        details.append(f"Attempts: {attempts} (journey was retried)")

    summary = str(journey.get("summary") or "").strip() or _STATE_NAME.get(state, str(state))

    # A pass that needed retries still hit a failure; hiding it would overstate availability.
    if attempts > 1 and state < CRIT:
        state = max(state, int(params.get("retried_state", WARN)))
        summary += f" (succeeded only after {attempts} attempts)"

    # An outdated result says nothing about the application now, so its state is replaced (not
    # escalated). UNKNOWN by default lets availability/SLA reporting exclude the gap.
    if stale_note is not None:
        state = int(params.get("staleness_state", UNKNOWN))
        summary = f"{stale_note}: {summary}"
    return JourneyOutcome(
        state=state, summary=summary, details=details, metrics=metrics, steps=steps
    )


# Applied without any "worker scheduler" rule, so a stalled executor always alerts.
WORKER_DEFAULT_PARAMETERS: dict[str, object] = {
    "heartbeat_age_levels": ("fixed", (600.0, 1800.0)),
}


@dataclass
class WorkerOutcome:
    state: int
    summary: str
    details: list[str] = field(default_factory=list)
    metrics: list[MetricSpec] = field(default_factory=list)


def evaluate_worker(worker: dict, params: Mapping, now: float) -> WorkerOutcome:
    heartbeat_at = worker.get("heartbeat_at")
    if heartbeat_at is None:
        return WorkerOutcome(state=UNKNOWN, summary="No scheduler heartbeat reported")

    state = OK
    details: list[str] = []
    metrics: list[MetricSpec] = []

    age = now - _f(heartbeat_at)
    age_levels = norm_levels(params.get("heartbeat_age_levels"))
    metrics.append(MetricSpec("synmon_heartbeat_age", age, age_levels))
    state = max(state, level_state(age, age_levels))

    found = int(_f(worker.get("results_found")))
    failed = int(_f(worker.get("journeys_failed")))
    skipped = int(_f(worker.get("journeys_skipped")))
    unparseable = int(_f(worker.get("unparseable")))
    metrics.append(MetricSpec("synmon_results_found", found))
    metrics.append(MetricSpec("synmon_journeys_failed", failed))
    metrics.append(MetricSpec("synmon_journeys_skipped", skipped))
    metrics.append(MetricSpec("synmon_unparseable", unparseable))

    if unparseable:
        state = max(state, WARN)
        details.append(f"{unparseable} unparseable spool file(s)")

    summary = f"Scheduler heartbeat {int(age)}s ago; {found} result(s), {failed} failed"
    if skipped:
        state = max(state, WARN)
        summary += f", {skipped} skipped (run budget exhausted)"
    raw_errors = worker.get("load_errors")
    load_errors = [str(e) for e in raw_errors] if isinstance(raw_errors, list) else []
    if load_errors:
        state = max(state, WARN)
        summary += f"; {len(load_errors)} journey file(s) failed to load"
        details.extend(load_errors)
    not_allowed = int(_f(worker.get("not_allowed")))
    if not_allowed:
        state = max(state, WARN)
        summary += f"; {not_allowed} result(s) for hosts not in the allowlist dropped"
    overflow = int(_f(worker.get("overflow")))
    if overflow:
        state = max(state, WARN)
        summary += f"; {overflow} spool file(s) not read (agent plugin read limit reached)"
    # Absent (older agent plugin) says nothing; only an explicit False means "no allowlist".
    if worker.get("allowlist") is False:
        state = max(state, WARN)
        summary += "; no target-host allowlist"
        details.append(
            "Without /etc/synmon/allowed_hosts on the worker, a compromised executor could send "
            "piggyback data to any host (deploy/install.sh --allowed-hosts creates it)."
        )
    run_error = worker.get("run_error")
    if run_error:
        # The whole run failed, so every journey is going stale; say why here.
        state = CRIT
        summary += f"; last run failed: {run_error}"
    return WorkerOutcome(state=state, summary=summary, details=details, metrics=metrics)

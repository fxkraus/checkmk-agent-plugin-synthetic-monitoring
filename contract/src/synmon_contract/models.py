"""Normalized result contract models. No Playwright/OS imports allowed."""

from __future__ import annotations

from enum import IntEnum

from pydantic import BaseModel, ConfigDict, Field

SCHEMA_VERSION = "1.0.0"

# Checkmk host-name characters only: the agent plugin writes target_host into a piggyback header.
TARGET_HOST_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._-]{0,252}$"


class Status(IntEnum):
    OK = 0
    WARN = 1
    CRIT = 2
    UNKNOWN = 3


class _Base(BaseModel):
    # Lenient consumer: ignore unknown fields so minor-version producers stay compatible.
    model_config = ConfigDict(extra="ignore")


class Vitals(_Base):
    """Web performance metrics (Core Web Vitals + supporting timings). Times in milliseconds."""

    lcp_ms: float | None = None
    fcp_ms: float | None = None
    ttfb_ms: float | None = None
    inp_ms: float | None = None
    cls: float | None = None


class Step(_Base):
    name: str
    status: int = Field(ge=0, le=3)
    duration_ms: int = Field(ge=0)
    message: str | None = None
    started_at: float | None = None
    vitals: Vitals | None = None


class Artifacts(_Base):
    screenshot_path: str | None = None
    trace_path: str | None = None


class JourneyError(_Base):
    type: str
    message: str
    step: str | None = None


class JourneyResult(_Base):
    schema_version: str = SCHEMA_VERSION
    executor: str
    executor_version: str
    worker_id: str
    target_host: str = Field(pattern=TARGET_HOST_PATTERN)
    journey_name: str
    journey_id: str
    status: int = Field(ge=0, le=3)
    summary: str
    started_at: float
    finished_at: float | None = None
    duration_ms: int = Field(ge=0)
    max_age_s: int = Field(ge=0)
    interval_s: int = Field(ge=0)
    steps: list[Step] = Field(default_factory=list)
    artifacts: Artifacts = Field(default_factory=Artifacts)
    error: JourneyError | None = None
    vitals: Vitals | None = None
    labels: dict[str, str] = Field(default_factory=dict)
    attempts: int = Field(default=1, ge=1)


class Heartbeat(_Base):
    """Written by the executor each run; read by the agent plugin."""

    schema_version: str = SCHEMA_VERSION
    worker_id: str
    executor: str
    executor_version: str
    heartbeat_at: float
    last_run_started_at: float | None = None
    last_run_finished_at: float | None = None
    last_run_duration_ms: int | None = None
    journeys_run: int = 0
    journeys_failed: int = 0
    journeys_skipped: int = 0
    load_errors: list[str] = Field(default_factory=list)
    # Set when the run itself failed (e.g. the browser did not start), not a single journey.
    run_error: str | None = None


class WorkerHealth(_Base):
    """The `synmon_worker` section payload: heartbeat fields + agent-computed scan counts."""

    schema_version: str = SCHEMA_VERSION
    worker_id: str | None = None
    executor: str | None = None
    executor_version: str | None = None
    heartbeat_at: float | None = None
    last_run_started_at: float | None = None
    last_run_finished_at: float | None = None
    last_run_duration_ms: int | None = None
    journeys_run: int | None = None
    journeys_failed: int | None = None
    journeys_skipped: int | None = None
    load_errors: list[str] = Field(default_factory=list)
    run_error: str | None = None
    results_found: int = 0
    unparseable: int = 0

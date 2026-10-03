"""Executor configuration from ``SYNMON_*`` environment variables, validated up front."""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError

DEFAULT_ARTIFACT_MAX_AGE_S = 7 * 24 * 3600


class ExecutorConfig(BaseModel):
    # Field aliases are the environment variable names, so validation errors name them.
    model_config = ConfigDict(extra="ignore", frozen=True, populate_by_name=True)

    worker_id: str = Field(default_factory=lambda: os.uname().nodename, alias="SYNMON_WORKER_ID")
    journeys_dir: Path = Field(default=Path("/journeys"), alias="SYNMON_JOURNEYS_DIR")
    spool_dir: Path = Field(default=Path("/var/lib/synmon/spool"), alias="SYNMON_SPOOL_DIR")
    artifacts_dir: Path = Field(
        default=Path("/var/lib/synmon/artifacts"), alias="SYNMON_ARTIFACTS_DIR"
    )
    heartbeat_path: Path = Field(
        default=Path("/var/lib/synmon/heartbeat.json"), alias="SYNMON_HEARTBEAT_PATH"
    )
    # Traces record typed passwords and session cookies: opt-in for debugging only.
    trace: bool = Field(default=False, alias="SYNMON_TRACE")
    # Chromium's own (user-namespace) sandbox; needs CAP_SYS_CHROOT in the container's bounding
    # set (install.sh --chromium-sandbox) and a seccomp profile that allows unshare.
    chromium_sandbox: bool = Field(default=False, alias="SYNMON_CHROMIUM_SANDBOX")
    retries: int = Field(default=1, ge=0, alias="SYNMON_RETRIES")
    timeout_s: float = Field(default=120.0, gt=0, allow_inf_nan=False, alias="SYNMON_TIMEOUT_S")
    retry_backoff_s: float = Field(
        default=1.0, ge=0, allow_inf_nan=False, alias="SYNMON_RETRY_BACKOFF_S"
    )
    run_budget_s: float | None = Field(
        default=None, gt=0, allow_inf_nan=False, alias="SYNMON_RUN_BUDGET_S"
    )
    artifact_max_age_s: int = Field(
        default=DEFAULT_ARTIFACT_MAX_AGE_S, ge=0, alias="SYNMON_ARTIFACT_MAX_AGE_S"
    )

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> ExecutorConfig:
        """Unset or empty variables take the default. Raises ``ValidationError``."""
        values: dict[str, object] = {k: v for k, v in env.items() if k.startswith("SYNMON_") and v}
        for flag in ("SYNMON_TRACE", "SYNMON_CHROMIUM_SANDBOX"):
            if flag in values:
                values[flag] = values[flag] == "1"
        return cls.model_validate(values)


def describe(exc: ValidationError) -> str:
    """One line naming each invalid variable, e.g. ``SYNMON_RETRIES: Input should be ...``."""
    return "; ".join(
        f"{'.'.join(str(p) for p in err['loc'])}: {err['msg']}" for err in exc.errors()
    )

"""Journey authoring SDK: the `@journey` decorator and the per-step recorder."""

from __future__ import annotations

import re
import time
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field

JourneyFunc = Callable[..., Awaitable[None]]


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "journey"


@dataclass
class JourneyDef:
    name: str
    journey_id: str
    target_host: str
    max_age_s: int
    interval_s: int
    func: JourneyFunc
    labels: dict[str, str] = field(default_factory=dict)
    retries: int | None = None
    timeout_s: float | None = None


_REGISTRY: list[JourneyDef] = []


def journey(
    *,
    name: str,
    target_host: str,
    max_age_s: int,
    interval_s: int,
    journey_id: str | None = None,
    labels: dict[str, str] | None = None,
    retries: int | None = None,
    timeout_s: float | None = None,
) -> Callable[[JourneyFunc], JourneyFunc]:
    def decorator(func: JourneyFunc) -> JourneyFunc:
        _REGISTRY.append(
            JourneyDef(
                name=name,
                journey_id=journey_id or slugify(name),
                target_host=target_host,
                max_age_s=max_age_s,
                interval_s=interval_s,
                func=func,
                labels=dict(labels or {}),
                retries=retries,
                timeout_s=timeout_s,
            )
        )
        return func

    return decorator


def registered_journeys() -> list[JourneyDef]:
    return list(_REGISTRY)


@dataclass
class LoginDef:
    name: str
    login_id: str
    target_host: str
    max_age_s: int
    interval_s: int
    func: JourneyFunc
    labels: dict[str, str] = field(default_factory=dict)
    retries: int | None = None
    timeout_s: float | None = None

    @property
    def journey_id(self) -> str:
        return self.login_id


_LOGIN_REGISTRY: list[LoginDef] = []


def login(
    *,
    target_host: str,
    name: str = "login",
    max_age_s: int,
    interval_s: int,
    journey_id: str | None = None,
    labels: dict[str, str] | None = None,
    retries: int | None = None,
    timeout_s: float | None = None,
) -> Callable[[JourneyFunc], JourneyFunc]:
    def decorator(func: JourneyFunc) -> JourneyFunc:
        _LOGIN_REGISTRY.append(
            LoginDef(
                name=name,
                login_id=journey_id or slugify(name),
                target_host=target_host,
                max_age_s=max_age_s,
                interval_s=interval_s,
                func=func,
                labels=dict(labels or {}),
                retries=retries,
                timeout_s=timeout_s,
            )
        )
        return func

    return decorator


def registered_logins() -> list[LoginDef]:
    return list(_LOGIN_REGISTRY)


def clear_registry() -> None:
    _REGISTRY.clear()
    _LOGIN_REGISTRY.clear()


def truncate_registry(journeys: int, logins: int) -> None:
    """Drop registrations made after the registries had these lengths."""
    del _REGISTRY[journeys:]
    del _LOGIN_REGISTRY[logins:]


@dataclass
class StepRecord:
    name: str
    status: int
    duration_ms: int
    message: str | None
    started_at: float
    vitals: dict | None = None


class StepRecorder:
    def __init__(
        self,
        wall: Callable[[], float] = time.time,
        mono: Callable[[], float] = time.monotonic,
        vitals_reader: Callable[[], Awaitable[dict | None]] | None = None,
    ) -> None:
        self._wall = wall
        self._mono = mono
        self._vitals_reader = vitals_reader
        self.steps: list[StepRecord] = []
        self.last_failed_step: str | None = None

    async def _read_vitals(self) -> dict | None:
        if self._vitals_reader is None:
            return None
        try:
            return await self._vitals_reader()
        except Exception:
            return None

    @asynccontextmanager
    async def step(self, name: str):
        started_at = self._wall()
        t0 = self._mono()
        try:
            yield
        except Exception as exc:
            self.last_failed_step = name
            snap = await self._read_vitals()
            self.steps.append(
                StepRecord(
                    name=name,
                    status=2,
                    duration_ms=int((self._mono() - t0) * 1000),
                    message=f"{type(exc).__name__}: {exc}",
                    started_at=started_at,
                    vitals=snap,
                )
            )
            raise
        else:
            snap = await self._read_vitals()
            self.steps.append(
                StepRecord(
                    name=name,
                    status=0,
                    duration_ms=int((self._mono() - t0) * 1000),
                    message=None,
                    started_at=started_at,
                    vitals=snap,
                )
            )

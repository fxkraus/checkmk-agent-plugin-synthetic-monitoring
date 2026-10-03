"""Import journey modules from a directory so the @journey decorators register them."""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

from synmon_contract.models import TARGET_HOST_PATTERN

from synmon_executor.sdk import (
    JourneyDef,
    LoginDef,
    registered_journeys,
    registered_logins,
    truncate_registry,
)
from synmon_executor.spool import result_stem

_HOST_RE = re.compile(TARGET_HOST_PATTERN)


def _conflict(new: list[JourneyDef | LoginDef], old: list[JourneyDef | LoginDef]) -> str | None:
    """Why the module's registrations cannot be accepted, or ``None``."""
    stems = {result_stem(d.target_host, d.journey_id) for d in old}
    names = {(d.target_host, d.name) for d in old}
    logins = {d.target_host: d.name for d in old if isinstance(d, LoginDef)}
    for d in new:
        if not _HOST_RE.fullmatch(d.target_host):
            return f"invalid target_host {d.target_host!r} in '{d.name}'"
        if isinstance(d, LoginDef):
            # One session state per target host: a second login would silently replace it.
            if d.target_host in logins:
                return (
                    f"second login '{d.name}' for {d.target_host} "
                    f"(already has '{logins[d.target_host]}')"
                )
            logins[d.target_host] = d.name
        stem = result_stem(d.target_host, d.journey_id)
        if stem in stems:
            return f"'{d.name}' on {d.target_host} collides with another journey's id"
        if (d.target_host, d.name) in names:
            return f"duplicate journey name '{d.name}' on {d.target_host}"
        stems.add(stem)
        names.add((d.target_host, d.name))
    return None


def load_journeys(journeys_dir: Path) -> tuple[list[str], list[str]]:
    """Import every journey module; return (loaded module names, per-file load errors).

    A broken module must not stop the others from running, so each import is isolated.
    """
    loaded: list[str] = []
    errors: list[str] = []
    for path in sorted(Path(journeys_dir).glob("*.py")):
        if path.name.startswith("_"):
            continue
        module_name = f"synmon_journey_{path.stem}"
        spec = importlib.util.spec_from_file_location(module_name, path)
        if spec is None or spec.loader is None:
            continue
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        before = len(registered_journeys()), len(registered_logins())
        try:
            spec.loader.exec_module(module)
        except Exception as exc:
            sys.modules.pop(module_name, None)
            # Decorators that ran before the failure must not leave half-configured journeys.
            truncate_registry(*before)
            errors.append(f"{path.name}: {type(exc).__name__}: {exc}")
            continue
        journeys, logins = registered_journeys(), registered_logins()
        old: list[JourneyDef | LoginDef] = [*journeys[: before[0]], *logins[: before[1]]]
        new: list[JourneyDef | LoginDef] = [*journeys[before[0] :], *logins[before[1] :]]
        conflict = _conflict(new, old)
        if conflict is not None:
            sys.modules.pop(module_name, None)
            truncate_registry(*before)
            errors.append(f"{path.name}: {conflict}")
            continue
        loaded.append(module_name)
    return loaded, errors

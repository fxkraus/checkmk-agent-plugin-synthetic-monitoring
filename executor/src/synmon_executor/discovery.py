"""Import journey modules from a directory so the @journey decorators register them."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from synmon_executor.sdk import registered_journeys, registered_logins, truncate_registry


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
        loaded.append(module_name)
    return loaded, errors

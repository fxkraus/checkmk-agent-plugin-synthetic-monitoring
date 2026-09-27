"""Generate the committed JSON Schema from the Pydantic models."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from synmon_contract.models import JourneyResult, WorkerHealth

_MODELS: dict[str, type[BaseModel]] = {
    "synmon_result.schema.json": JourneyResult,
    "synmon_worker.schema.json": WorkerHealth,
}


def render() -> dict[str, str]:
    """Return {filename: file-text}; deterministic so it can be diffed in CI."""
    out: dict[str, str] = {}
    for name, model in _MODELS.items():
        schema: dict[str, Any] = model.model_json_schema()
        out[name] = json.dumps(schema, indent=2, sort_keys=True) + "\n"
    return out


def export(out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, text in render().items():
        (out_dir / name).write_text(text, encoding="utf-8")


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("schema")
    export(out)


if __name__ == "__main__":
    main()

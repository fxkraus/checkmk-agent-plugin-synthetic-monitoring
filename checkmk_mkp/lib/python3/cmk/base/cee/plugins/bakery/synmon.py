"""Agent Bakery plugin: deploy the synmon agent plugin to worker hosts (commercial editions only).

Bakery API v1 plug-ins are loaded only from ``cmk.base.cee.plugins.bakery`` (still honoured by
2.5 for third-party plug-ins), so this ships in the MKP ``lib`` part, not under ``cmk_addons``.
"""

from collections.abc import Iterable, Mapping
from pathlib import Path

from cmk.base.plugins.bakery.bakery_api.v1 import OS, Plugin, register


def _get_synmon_files(conf: Mapping[str, object]) -> Iterable[Plugin]:
    interval = conf.get("interval")
    yield Plugin(
        base_os=OS.LINUX,
        source=Path("synmon_collector.py"),
        interval=int(interval) if interval is not None else None,
    )


register.bakery_plugin(
    name="synmon",
    files_function=_get_synmon_files,
)

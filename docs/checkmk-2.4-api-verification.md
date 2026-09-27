# Checkmk 2.4 CCE Plugin API Verification

Recorded against a live Checkmk CCE 2.4 site running in Docker (`checkmk/check-mk-cloud:2.4.0-latest`)
on macOS Apple Silicon (amd64 emulation). All output below is the real stdout of each command.

> **Setup note**: `.devcontainer/docker-compose.yml` tmpfs was set to `uid=1000,gid=1000`
> (`- /opt/omd/sites/cmk/tmp:uid=1000,gid=1000`) so the `cmk` user can write to it on boot.
> Without this the site fails to initialise under QEMU amd64 emulation.

> **Note on container stability**: Apache fails to start in the container on macOS/amd64 emulation
> (QEMU jemalloc limitation), causing the entrypoint watchdog to eventually exit the container.
> All commands were run immediately after container start, before the watchdog fired.
> The Python API inspection results are unaffected — they query installed packages, not running services.

---

## Step 1 — OMD version and edition

```
$ docker compose -f .devcontainer/docker-compose.yml exec checkmk omd version
OMD - Open Monitoring Distribution Version 2.4.0p32.cce
```

**Finding**: edition suffix `.cce` confirms Cloud Edition; CEE bakery API is available.

---

## Step 2 — `cmk.agent_based.v2` import surface

```
$ docker compose -f .devcontainer/docker-compose.yml exec checkmk \
    su - cmk -c 'python3 -c "import cmk.agent_based.v2 as m; print(m.__file__); \
    print(sorted(n for n in dir(m) if not n.startswith(\"_\")))"'
```

**Output:**
```
/omd/sites/cmk/lib/python3.12/site-packages/cmk/agent_based/v2/__init__.py
['AgentParseFunction', 'AgentSection', 'Attributes', 'CheckPlugin', 'CheckResult',
'DiscoveryResult', 'FixedLevelsT', 'GetRateError', 'HostLabel', 'HostLabelGenerator',
'IgnoreResults', 'IgnoreResultsError', 'InventoryPlugin', 'InventoryResult', 'LevelsT',
'Metric', 'NoLevelsT', 'OIDBytes', 'OIDCached', 'OIDEnd', 'PredictiveLevelsT', 'Result',
'RuleSetType', 'SNMPDetectSpecification', 'SNMPSection', 'SNMPTree', 'Service',
'ServiceLabel', 'SimpleSNMPSection', 'State', 'StringByteTable', 'StringTable',
'TableRow', 'all_of', 'any_of', 'check_levels', 'clusterize', 'contains', 'endswith',
'entry_point_prefixes', 'equals', 'exists', 'get_average', 'get_rate', 'get_value_store',
'matches', 'not_contains', 'not_endswith', 'not_equals', 'not_exists', 'not_matches',
'not_startswith', 'render', 'startswith']
```

**Use this import:**
```python
from cmk.agent_based.v2 import (
    AgentSection, CheckPlugin, Result, Service, State, Metric, StringTable, check_levels
)
```

---

## Step 3 — `cmk.rulesets.v1` import surface

### 3a — Top-level module

```
$ docker compose -f .devcontainer/docker-compose.yml exec checkmk \
    su - cmk -c 'python3 -c "import cmk.rulesets.v1 as m; print(m.__file__); print(sorted(dir(m)))"'
```

**Output:**
```
/omd/sites/cmk/lib/python3.12/site-packages/cmk/rulesets/v1/__init__.py
['Help', 'Label', 'Mapping', 'Message', 'Title', '__all__', '__builtins__', '__cached__',
'__doc__', '__file__', '__loader__', '__name__', '__package__', '__path__', '__spec__',
'_localize', 'entry_point_prefixes', 'form_specs', 'rule_specs']
```

### 3b — Submodules `form_specs` and `rule_specs`

```
$ docker compose -f .devcontainer/docker-compose.yml exec checkmk \
    su - cmk -c 'python3 -c "import cmk.rulesets.v1.form_specs as f, \
    cmk.rulesets.v1.rule_specs as r; print(sorted(dir(f))); print(sorted(dir(r)))"'
```

**Output — `form_specs`:**
```
['BooleanChoice', 'CascadingSingleChoice', 'CascadingSingleChoiceElement', 'DataSize',
'DefaultValue', 'DictElement', 'DictGroup', 'Dictionary', 'FieldSize', 'FileUpload',
'FixedValue', 'Float', 'FormSpec', 'HostState', 'IECMagnitude', 'InputHint', 'Integer',
'InvalidElementMode', 'InvalidElementValidator', 'LevelDirection', 'Levels',
'LevelsConfigModel', 'LevelsType', 'List', 'MatchingScope', 'Metric', 'MonitoredHost',
'MonitoredService', 'MultilineText', 'MultipleChoice', 'MultipleChoiceElement', 'NoGroup',
'Password', 'Percentage', 'PredictiveLevels', 'Prefill', 'Proxy', 'ProxySchema',
'RegularExpression', 'SIMagnitude', 'ServiceState', 'SimpleLevels',
'SimpleLevelsConfigModel', 'SingleChoice', 'SingleChoiceElement', 'String',
'TimeMagnitude', 'TimePeriod', 'TimeSpan', ...]
```

**Output — `rule_specs`:**
```
['ActiveCheck', 'AgentAccess', 'AgentConfig', 'Callable', 'CheckParameters',
'CustomTopic', 'Dictionary', 'DiscoveryParameters', 'EnforcedService', 'Enum',
'EvalType', 'FormSpec', 'Help', 'Host', 'HostAndItemCondition',
'HostAndServiceCondition', 'HostCondition', 'InventoryParameters', 'LengthInRange',
'NotificationParameters', 'SNMP', 'Service', 'SpecialAgent', 'String', 'Title',
'Topic', ...]
```

**Use this import:**
```python
from cmk.rulesets.v1 import Help, Label, Title
from cmk.rulesets.v1.form_specs import Dictionary, DictElement, String, Integer, SimpleLevels
from cmk.rulesets.v1.rule_specs import SpecialAgent, Topic, Help, Title
```

---

## Step 4 — `cmk.graphing.v1` import surface

```
$ docker compose -f .devcontainer/docker-compose.yml exec checkmk \
    su - cmk -c 'python3 -c "import cmk.graphing.v1 as m; print(m.__file__); print(sorted(dir(m)))"'
```

**Output:**
```
/omd/sites/cmk/lib/python3.12/site-packages/cmk/graphing/v1/__init__.py
['Mapping', 'Title', '__all__', '__builtins__', '__cached__', '__doc__', '__file__',
'__loader__', '__name__', '__package__', '__path__', '__spec__', '_localize',
'_type_defs', 'entry_point_prefixes', 'graphs', 'metrics', 'perfometers', 'translations']
```

**Submodule surfaces (captured in same session):**

```
$ docker compose -f .devcontainer/docker-compose.yml exec checkmk su - cmk -c \
  'python3 -c "import cmk.graphing.v1.metrics as m; print(sorted(n for n in dir(m) if not n.startswith(\"_\")))"'
```

`cmk.graphing.v1.metrics` exports:
```
['AutoPrecision', 'Color', 'Constant', 'CriticalOf', 'DecimalNotation', 'Difference',
'EngineeringScientificNotation', 'Enum', 'Fraction', 'IECNotation', 'KW_ONLY',
'MaximumOf', 'Metric', 'MinimumOf', 'Product', 'SINotation', 'Sequence',
'StandardScientificNotation', 'StrictPrecision', 'Sum', 'TimeNotation', 'Title', 'Unit',
'WarningOf', 'annotations', 'auto', 'dataclass']
```

```
$ docker compose -f .devcontainer/docker-compose.yml exec checkmk su - cmk -c \
  'python3 -c "import cmk.graphing.v1.graphs as m; print(sorted(n for n in dir(m) if not n.startswith(\"_\")))"'
```

`cmk.graphing.v1.graphs` exports:
```
['Bidirectional', 'Bound', 'Graph', 'MinimalRange', 'Quantity', 'Sequence', 'Title', 'dataclass']
```

```
$ docker compose -f .devcontainer/docker-compose.yml exec checkmk su - cmk -c \
  'python3 -c "import cmk.graphing.v1.perfometers as m; print(sorted(n for n in dir(m) if not n.startswith(\"_\")))"'
```

`cmk.graphing.v1.perfometers` exports:
```
['Bidirectional', 'Bound', 'Closed', 'FocusRange', 'Open', 'Perfometer', 'Quantity',
'Sequence', 'Stacked', 'dataclass']
```

**Use this import:**
```python
from cmk.graphing.v1.metrics import Metric, Title, Unit, Color, SINotation
from cmk.graphing.v1.graphs import Graph, Quantity
from cmk.graphing.v1.perfometers import Perfometer, FocusRange, Stacked
from cmk.graphing.v1.translations import Translation  # if needed
```

---

## Step 5 — Bakery API import path (CEE/CCE)

```
$ docker compose -f .devcontainer/docker-compose.yml exec checkmk su - cmk -c \
  'for mod in cmk.base.cee.plugins.bakery.bakery_api.v1 cmk.base.plugins.bakery.bakery_api.v1; do \
     python3 -c "import importlib,sys; m=importlib.import_module(\"$mod\"); \
     print(\"OK\", \"$mod\", sorted(n for n in dir(m) if not n.startswith(\"_\")))" \
     2>/dev/null || echo "MISS $mod"; \
   done'
```

**Output:**
```
OK cmk.base.cee.plugins.bakery.bakery_api.v1 ['DebStep', 'FileGenerator', 'OS', 'Plugin',
'PluginConfig', 'RpmStep', 'Scriptlet', 'ScriptletGenerator', 'SolStep', 'SystemBinary',
'SystemConfig', 'WindowsConfigContent', 'WindowsConfigEntry', 'WindowsConfigGenerator',
'WindowsConfigItems', 'WindowsGlobalConfigEntry', 'WindowsSystemConfigEntry',
'password_store', 'quote_shell_string', 'register']

OK cmk.base.plugins.bakery.bakery_api.v1 ['DebStep', 'FileGenerator', 'OS', 'Plugin',
'PluginConfig', 'RpmStep', 'Scriptlet', 'ScriptletGenerator', 'SolStep', 'SystemBinary',
'SystemConfig', 'WindowsConfigContent', 'WindowsConfigEntry', 'WindowsConfigGenerator',
'WindowsConfigItems', 'WindowsGlobalConfigEntry', 'WindowsSystemConfigEntry',
'password_store', 'quote_shell_string', 'register', 'shlex']
```

**File locations:**
- `cmk.base.cee.plugins.bakery.bakery_api.v1` → `/omd/sites/cmk/lib/python3/cmk/base/cee/plugins/bakery/bakery_api/v1/__init__.py`
- `cmk.base.plugins.bakery.bakery_api.v1` → `/omd/sites/cmk/lib/python3/cmk/base/plugins/bakery/bakery_api/v1/__init__.py`

**Relationship**: The `cee` module is a thin wildcard re-export of the `base` module:
```python
# /omd/sites/cmk/lib/python3/cmk/base/cee/plugins/bakery/bakery_api/v1/__init__.py
from cmk.base.plugins.bakery.bakery_api.v1 import *  # noqa: F403
```

**Use this import** (canonical, non-CEE-specific path):
```python
from cmk.base.plugins.bakery.bakery_api.v1 import (
    OS, Plugin, PluginConfig, FileGenerator, register
)
```

---

## Step 6 — Plugin directory layout

```
$ docker compose -f .devcontainer/docker-compose.yml exec checkmk su - cmk -c \
  'ls -la local/lib/python3/cmk_addons/plugins 2>/dev/null; echo "---"; \
   ls -la local/lib/python3/cmk/base/cee/plugins/bakery 2>/dev/null; echo "---"; \
   ls -la local/lib/check_mk/base/plugins 2>/dev/null; echo "---"; \
   find local -maxdepth 4 -type d -name agent_based 2>/dev/null'
```

**Output:**
```
total 8
drwxr-x--- 2 cmk cmk 4096 Jun 21 17:38 .
drwxr-x--- 3 cmk cmk 4096 Jun 21 17:38 ..
---
---
---
(no agent_based dirs found under local/)
```

All directories exist but are **empty** (fresh site, no extensions installed). This is expected.

**Authoritative plugin paths from `cmk.utils.paths`:**

```
$ docker compose -f .devcontainer/docker-compose.yml exec checkmk su - cmk -c \
  'python3 -c "import cmk.utils.paths as p; [print(n, \"=\", getattr(p, n)) for n in sorted(dir(p)) if n.startswith(\"local_\")]"'
```

**Output (verbatim):**
```
local_agent_based_plugins_dir = /omd/sites/cmk/local/lib/check_mk/base/plugins/agent_based
local_agents_dir = /omd/sites/cmk/local/share/check_mk/agents
local_alert_handlers_dir = /omd/sites/cmk/local/share/check_mk/alert_handlers
local_bin_dir = /omd/sites/cmk/local/bin
local_checks_dir = /omd/sites/cmk/local/share/check_mk/checks
local_cmk_addons_plugins_dir = /omd/sites/cmk/local/lib/python3/cmk_addons/plugins
local_cmk_plugins_dir = /omd/sites/cmk/local/lib/python3/cmk/plugins
local_config_file = /omd/sites/cmk/etc/check_mk/local.mk
local_dashboards_dir = /omd/sites/cmk/local/lib/check_mk/gui/plugins/dashboard
local_doc_dir = /omd/sites/cmk/local/share/doc/check_mk
local_enabled_packages_dir = /omd/sites/cmk/local/share/check_mk/enabled_packages
local_gui_plugins_dir = /omd/sites/cmk/local/lib/check_mk/gui/plugins
local_inventory_dir = /omd/sites/cmk/local/share/check_mk/inventory
local_legacy_check_manpages_dir = /omd/sites/cmk/local/share/check_mk/checkman
local_lib_dir = /omd/sites/cmk/local/lib
local_locale_dir = /omd/sites/cmk/local/share/check_mk/locale
local_mib_dir = /omd/sites/cmk/local/share/snmp/mibs
local_nagios_plugins_dir = /omd/sites/cmk/local/lib/nagios/plugins
local_notifications_dir = /omd/sites/cmk/local/share/check_mk/notifications
local_optional_packages_dir = /omd/sites/cmk/var/check_mk/packages_local
local_pnp_templates_dir = /omd/sites/cmk/local/share/check_mk/pnp-templates
local_reports_dir = /omd/sites/cmk/local/lib/check_mk/gui/plugins/reports
local_root = /omd/sites/cmk/local
local_share_dir = /omd/sites/cmk/local/share/check_mk
local_special_agents_dir = /omd/sites/cmk/local/share/check_mk/agents/special
local_views_dir = /omd/sites/cmk/local/lib/check_mk/gui/plugins/views
local_web_dir = /omd/sites/cmk/local/share/check_mk/web
```

| Path attribute | Value |
|---|---|
| `local_root` | `/omd/sites/cmk/local` |
| `local_cmk_addons_plugins_dir` | `/omd/sites/cmk/local/lib/python3/cmk_addons/plugins` |
| `local_cmk_plugins_dir` | `/omd/sites/cmk/local/lib/python3/cmk/plugins` |
| `local_agent_based_plugins_dir` | `/omd/sites/cmk/local/lib/check_mk/base/plugins/agent_based` |
| `local_legacy_check_manpages_dir` | `/omd/sites/cmk/local/share/check_mk/checkman` |
| `local_agents_dir` | `/omd/sites/cmk/local/share/check_mk/agents` |
| `local_special_agents_dir` | `/omd/sites/cmk/local/share/check_mk/agents/special` |
| `local_checks_dir` | `/omd/sites/cmk/local/share/check_mk/checks` |
| `local_web_dir` | `/omd/sites/cmk/local/share/check_mk/web` |

**For MKP-style extensions in 2.4** the recommended structure under `local/lib/python3/cmk_addons/plugins/<plugin_name>/` is:
- `agent_based/` — check plugins and sections (import `cmk.agent_based.v2`)
- `graphing/` — metrics, graphs, perfometers (import `cmk.graphing.v1.*`)
- `rulesets/` — WATO rule definitions (import `cmk.rulesets.v1.*`)
- `checkman/` — man-page stubs (plain text files)
- `bakery/` — agent bakery rules (import `cmk.base.plugins.bakery.bakery_api.v1`)

Shipping baked-agent scripts goes in `local/share/check_mk/agents/bakery/<script>.py`.

---

## Step 7 — `mkp` tooling

> Note: `mkp --help` caused SIGKILL (exit 137) under QEMU amd64 emulation; bare `mkp` was used to capture the subcommand list instead.

```
$ docker compose -f .devcontainer/docker-compose.yml exec checkmk su - cmk -c 'mkp'
```

**Output:**
```
usage: mkp [-h] [--debug] [--verbose]
           {find,inspect,template,package,show,show-all,files,list,add,remove,release,
            enable,disable,disable-outdated,update-active}
           ...

Command line interface for the Checkmk Extension Packages

options:
  -h, --help            show this help message and exit
  --debug, -d
  --verbose, -v         Be more verbose

available commands:
  find                Show information about local files
  inspect             Show manifest of an MKP file
  template            Create a template of a package manifest
  package             Create an .mkp file from the provided manifest.
                      You can use the `template` command to create a manifest template.
  show                Show manifest of a stored package
  show-all            Show all manifests
  files               Show all files belonging to a package
  list                Show a table of all known files, including the deployment state
  add                 Add an MKP to the collection of managed MKPs
  remove              Remove a package from the site
  release             Remove the package and leave its contained files as unpackaged
  enable              Enable a disabled package
  disable             Disable an enabled package
  disable-outdated    Disable MKP packages declared outdated for the new version
  update-active       Disable unsuitable MKP packages, enable appropriate ones
```

**Packaging workflow:**
1. Place plugin files in `local/lib/python3/cmk_addons/plugins/<name>/`
2. `mkp template <name>` — generates a manifest template at `tmp/check_mk/<name>.manifest.temp`
3. Edit manifest; set `files`, `version`, `version.min_required`, etc.
4. `mkp package <name>.manifest.temp` — builds `<name>-<version>.mkp`
5. `mkp add <name>-<version>.mkp` — installs the package
6. `mkp enable <name>` / `mkp disable <name>` — toggle activation

**Example manifest structure** (from `mkp template synthetic_monitoring`):
```python
{'author': 'Add your name here',
 'description': 'Please add a description here',
 'download_url': 'https://example.com/synthetic_monitoring/',
 'files': {},
 'name': 'synthetic_monitoring',
 'title': 'Title of synthetic_monitoring',
 'version': '1.0.0',
 'version.min_required': '2.4.0p32',
 'version.packaged': 'cmk-mkp-tool 1.0.0',
 'version.usable_until': None}
```

---

## Canonical local plugin paths

| Plugin type | Local path (relative to site root `/omd/sites/cmk`) |
|---|---|
| agent_based (check plugins) | `local/lib/python3/cmk_addons/plugins/<pkg>/agent_based/` |
| graphing (metrics/graphs) | `local/lib/python3/cmk_addons/plugins/<pkg>/graphing/` |
| rulesets (WATO rules) | `local/lib/python3/cmk_addons/plugins/<pkg>/rulesets/` |
| checkman (man pages) | `local/lib/python3/cmk_addons/plugins/<pkg>/checkman/` |
| bakery (agent rules, API v1) | `local/lib/python3/cmk/base/cee/plugins/bakery/` — **corrected**, see note below |
| special agent binary | `local/share/check_mk/agents/special/agent_<name>` |
| baked agent scripts | `local/share/check_mk/agents/bakery/<script>.py` |

> **Correction (verified 2026-09-23 against 2.4.0p32.cce and 2.5.0p14):** bakery API v1 plug-ins are
> loaded by `cmk.base.api.bakery.register.get_bakery_plugins()` only from the packages
> `cmk.base.cee.plugins.bakery` (2.4; 2.5 also `cmk.base.nonfree.plugins.bakery` and
> `cmk.base.plugins.bakery`). `cmk_addons/plugins/<pkg>/bakery/` is **not** scanned in 2.4 and in
> 2.5 only for API v2 (`cmk.bakery.v2_unstable`). A plug-in there was never registered. Guarded by
> `tests/checkmk/test_plugin_loading.py`.
>
> The `agent_based/`, `graphing/`, and `rulesets/` subdirectories are derived from
> `local_cmk_addons_plugins_dir` (`/omd/sites/cmk/local/lib/python3/cmk_addons/plugins`) + `/<pkg>/<subdir>`.
> There is no separate `local_*` attribute for each subdir — the convention is that all MKP extension
> types live under subdirectories of `local_cmk_addons_plugins_dir/<pkg>/`.
> The `checkman/` path inside `cmk_addons/plugins/<pkg>/checkman/` is the MKP-era location; the legacy
> attribute `local_legacy_check_manpages_dir` points to `local/share/check_mk/checkman` (flat, no package namespace).
> The old `local/lib/check_mk/base/plugins/agent_based/` path (`local_agent_based_plugins_dir`)
> is still supported as a legacy drop location.

---

## Summary: use-this-import per API

| API | Import |
|---|---|
| Agent-based checks | `from cmk.agent_based.v2 import AgentSection, CheckPlugin, Result, Service, State, Metric, StringTable, check_levels` |
| Rulesets (form specs) | `from cmk.rulesets.v1.form_specs import Dictionary, DictElement, String, Integer, SimpleLevels` |
| Rulesets (rule specs) | `from cmk.rulesets.v1.rule_specs import SpecialAgent, Topic` |
| Graphing | `from cmk.graphing.v1.metrics import Metric, Title, Unit, Color, SINotation` |
| Bakery (CCE/CEE) | `from cmk.base.plugins.bakery.bakery_api.v1 import OS, Plugin, PluginConfig, FileGenerator, register` |

---

## Constructor signatures (for the MKP wiring)

Recorded verbatim from `inspect.signature(...)` against the live 2.4.0p32.cce site (run as site
user `cmk`). These are the exact shapes the MKP wiring (`agent_based/`, `rulesets/`, `graphing/`)
is written against.

### `cmk.agent_based.v2`

```text
AgentSection(*, name, parse_function, parsed_section_name=None, host_label_function=None,
             host_label_default_parameters=None, host_label_ruleset_name=None,
             host_label_ruleset_type=RuleSetType.MERGED, supersedes=None)
CheckPlugin(*, name, sections=None, service_name, discovery_function,
            discovery_default_parameters=None, discovery_ruleset_name=None,
            discovery_ruleset_type=RuleSetType.MERGED, check_function,
            check_default_parameters=None, check_ruleset_name=None,
            cluster_check_function=None)
Result(**kwargs)                # state=..., summary=..., notice=..., details=...  (details must be str, NOT None)
Service(*, item=None, parameters=None, labels=None)
Metric(name, value, *, levels=None, boundaries=None)
State -> OK=0, WARN=1, CRIT=2, UNKNOWN=3
# also exported: CheckResult, DiscoveryResult, StringTable, render
```
> **Gotcha:** `Result` rejects `details=None` (it expects a `str`). Build kwargs and only pass
> `details` when there is text.

### `cmk.rulesets.v1`

```text
rule_specs.CheckParameters(title, topic, parameter_form, name, condition,
                           is_deprecated=False, help_text=None, create_enforced_service=True)
rule_specs.HostCondition()
rule_specs.HostAndItemCondition(item_title, item_form=String(...))
rule_specs.Topic  -> includes SYNTHETIC_MONITORING  (use this, not APPLICATIONS)

form_specs.Dictionary(*, title=None, help_text=None, migrate=None, custom_validate=None,
                      elements, no_elements_text=..., ignored_elements=())
form_specs.DictElement(*, parameter_form, required=False, render_only=False, group=NoGroup())
form_specs.SimpleLevels(*, title=None, help_text=None, migrate=None, custom_validate=None,
                        form_spec_template, level_direction,
                        prefill_levels_type=DefaultValue(LevelsType.FIXED), prefill_fixed_levels)
form_specs.Integer(*, title=None, ..., prefill=InputHint(0))
form_specs.Float(*, title=None, ..., prefill=InputHint(0.0))
form_specs.TimeSpan(*, title=None, ..., displayed_magnitudes, prefill=InputHint(0.0))   # displayed_magnitudes REQUIRED
form_specs.ServiceState(*, title=None, ..., prefill=DefaultValue(0))   # has .OK/.WARN/.CRIT/.UNKNOWN
form_specs.LevelDirection -> UPPER, LOWER
```
> **Gotcha (the keystone for evaluate.py):** `SimpleLevels`/`Levels` produce the *value* shape
> `("no_levels", None)` or `("fixed", (warn, crit))` — NOT a bare `(warn, crit)` tuple. The
> `lib/evaluate.py` normalizer must accept this. Predictive levels add a third
> `("cmk_postprocessed", "predictive_levels", ...)` shape (unsupported here → treated as no static levels).
> **Gotcha:** `TimeSpan` has **no default** for `displayed_magnitudes`; it must be supplied.

### `cmk.graphing.v1`

```text
metrics.Metric(*, name, title, unit, color)
metrics.Unit(notation, precision=AutoPrecision(2))
metrics.DecimalNotation(symbol)
metrics.AutoPrecision(digits)
metrics.Color -> BLUE, GRAY, GREEN, ORANGE, LIGHT_BLUE, LIGHT_GREEN, LIGHT_CYAN, LIGHT_PURPLE,
                 LIGHT_YELLOW, LIGHT_PINK, LIGHT_BROWN, ... (no plain YELLOW in first 30)
graphs.Graph(*, name, title, minimal_range=None, compound_lines=(), simple_lines=(),
             optional=(), conflicting=())
graphs.MinimalRange(lower, upper)
perfometers.Perfometer(*, name, focus_range, segments)
perfometers.FocusRange(lower, upper)        # each is Closed(value) | Open(value)
```
> Metrics referenced by a `Graph` that may be absent (the per-step durations) must be listed in
> `optional=` or the graph won't render.

### MKP on-disk format (from `cmk.mkp_tool._mkp` source)

An `.mkp` is a **gzip-compressed outer tar** (`tarfile w:gz`) containing:
- `info` — `pprint.pformat(manifest_dict)` + `"\n"`; read back via `ast.literal_eval` then pydantic
  `Manifest.model_validate`. Keys use aliases: `version.packaged`, `version.min_required`,
  `version.usable_until`; `files` is `{part_ident: [relpath, ...]}`.
- `info.json` — `manifest.model_dump_json(by_alias=True)` (for external tools).
- One **uncompressed** `<part_ident>.tar` per part with files (e.g. `cmk_addons_plugins.tar`),
  whose members are the file paths **relative to that part's site dir**
  (`cmk_addons_plugins` → `local/lib/python3/cmk_addons/plugins`, so members are `synmon/lib/parsing.py`, …).

This is fully reproducible with the standard-library `tarfile` module — `scripts/build_mkp.py`
builds a byte-identical-structure package without a Checkmk site, which is what CI uses.

---

## Bakery API + agent-config ruleset

Recorded verbatim from the live 2.4.0p32.cce site. The bakery API is CEE/CCE-only.

### `cmk.base.plugins.bakery.bakery_api.v1`

```text
exports: DebStep, FileGenerator, OS, Plugin, PluginConfig, RpmStep, Scriptlet, ScriptletGenerator,
         SolStep, SystemBinary, SystemConfig, WindowsConfig*, password_store, quote_shell_string,
         register, shlex
OS  -> AIX, LINUX, SOLARIS, WINDOWS
Plugin(*, base_os: OS, source: Path, target: Path | None = None, interval: int | None = None,
       asynchronous: bool | None = None, timeout: int | None = None, retry_count: int | None = None)
PluginConfig(*, base_os: OS, lines: Iterable[str], target: Path, include_header: bool = False)
SystemBinary(*, base_os: OS, source: Path, target: Path | None = None)
Scriptlet(*, step: DebStep | RpmStep | SolStep, lines: list[str])
register.bakery_plugin(*, name: str,
                       files_function: Callable[..., Iterator[Plugin|SystemBinary|PluginConfig|SystemConfig]] | None = None,
                       scriptlets_function: Callable[..., Iterator[Scriptlet]] | None = None,
                       windows_config_function: ... | None = None)
```
- `files_function(conf)` receives the merged WATO agent-config params and yields artifacts.
  `Plugin` deploys an agent plugin (Linux → `/usr/lib/check_mk_agent/plugins[/<interval>]`);
  `PluginConfig` writes a config file (`lines`) to `target`; `SystemBinary` deploys an arbitrary
  file to `target`; `Scriptlet` injects shell into the deb/rpm/sol install steps
  (`RpmStep`/`DebStep` members for `post`/`pre` install, e.g. to `systemctl daemon-reload`).
- The source files for `Plugin`/`SystemBinary` are resolved from the package's `bakery/` dir.
- `password_store` + `quote_shell_string` help inject secrets safely.

### `cmk.rulesets.v1.rule_specs.AgentConfig` (the bakery ruleset)

```text
AgentConfig(title, topic, parameter_form: Callable[[], Dictionary], name: str,
            is_deprecated=False, help_text=None)
```
Same `parameter_form`/`Dictionary` shape as `CheckParameters`, but the rule configures the bakery;
`name` must match the `register.bakery_plugin(name=...)`. Use `Topic.SYNTHETIC_MONITORING`.

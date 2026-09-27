# MKP Integration Verification (Checkmk 2.4 CCE)

Records the live verification of the `synmon` MKP against a running Checkmk CCE 2.4 site
(`checkmk/check-mk-cloud:2.4.0-latest`, reporting `2.4.0p32.cce`) on macOS Apple Silicon under
amd64 emulation. All output below is the real stdout of the commands.

## What was verified

The package built by `scripts/build_mkp.py` (`dist/synmon-1.0.0.mkp`) was copied into the site and
installed with the **real** `mkp` tool, then every `cmk.*` wiring module was imported (importing a
module executes its body, which constructs every `AgentSection`/`CheckPlugin`/`Metric`/`Graph`/
`Perfometer` and every ruleset `FormSpec` — so a bad constructor signature fails the import).

```text
$ mkp add /tmp/synmon-1.0.0.mkp
synmon 1.0.0
$ mkp enable synmon 1.0.0
$ mkp list | grep synmon
synmon 1.0.0   Synthetic Monitoring (Playwright) Synthetic Monitoring 2.4.0p32     None          9     Enabled (active on this site)
$ python3 -c "import …agent_based.synmon_journey, …agent_based.synmon_worker, \
                     …graphing.synmon, …rulesets.synmon_journey, …rulesets.synmon_worker; …"
journey check plugin: synmon_journey
worker check plugin : synmon_worker
journey ruleset     : synmon_journey
worker ruleset      : synmon_worker
step metrics        : 8
ALL WIRING IMPORTS OK
```

This confirms:

- **The hand-built `.mkp` is valid.** Checkmk's own `mkp add`/`mkp enable` accept the package
  produced by the stdlib builder — i.e. the reproduced on-disk format (`info` + `info.json` +
  `cmk_addons_plugins.tar`) is correct, and all 9 packaged files install to the right place.
- **Every wiring constructor matches the real 2.4 API.** The journey/worker check plugins, both
  WATO rulesets (exercising `SimpleLevels`, `TimeSpan(displayed_magnitudes=…)`,
  `ServiceState.WARN`, `Topic.SYNTHETIC_MONITORING`), and all graphing objects (duration/age
  metrics, 8 per-step metrics, perfometer, graphs) construct without error.
- **Producer/consumer field names align.** The worker section read by `evaluate_worker`
  (`heartbeat_at`, `results_found`, `journeys_failed`, `unparseable`) and the journey fields read
  by `evaluate_journey` (`status`, `summary`, `started_at`, `duration_ms`, `max_age_s`, `steps`,
  `artifacts`, `error`) exactly match `synmon_contract.models` (`WorkerHealth`/`JourneyResult`).

## Deferred

Full end-to-end **service discovery + check execution** against a piggyback host (feeding
`tests/server/integration/sample_agent_output.txt` through `cmk -II` / a check run) was **not**
completed here: the CCE container is unstable under amd64 emulation on macOS (Apache/QEMU crash,
the entrypoint watchdog exits the container ~60–90 s after boot), which is too short for the full
discovery flow. The parse → discover → status/staleness/threshold logic that discovery would
exercise is the stdlib `lib/` code, which is covered by 44 offline unit tests in `tests/server/`.

**Recommended before go-live:** run discovery + a check cycle on a native-amd64 Checkmk 2.4 site
(or a stable runner) using the committed `sample_agent_output.txt`, and confirm the
`Journey checkout`/`Journey login` services appear on `app.example.com` with CRIT/OK states and the
`Synthetic Worker Scheduler` service on the worker host.

## Bakery layer (MKP 1.1.0)

The 1.1.0 package (which adds the Agent Bakery plugin + ruleset and ships the agent plugin under
the `agents` part) was installed and its bakery wiring imported on the same live site:

```text
$ mkp add /tmp/synmon-1.1.0.mkp && mkp enable synmon 1.1.0
$ mkp list | grep synmon
synmon 1.1.0  Synthetic Monitoring (Playwright)  Synthetic Monitoring  2.4.0p32  None  12  Enabled (active on this site)
$ ls -l $OMD_ROOT/local/share/check_mk/agents/plugins/synmon_collector.py
-rwx------ 1 cmk cmk 2737 ... synmon_collector.py        # baked agent plugin landed
$ python3 -c "import …bakery.synmon, …rulesets.synmon_bakery; …"
bakery ruleset name : synmon
ALL BAKERY IMPORTS OK
```

Confirms the bakery `register.bakery_plugin` + `Plugin` and the `AgentConfig` ruleset constructors
are correct against the real API, and the `agents` package part installs the collector to the
agent share dir (where the bakery sources it). **Deferred:** an actual bake against an enrolled
agent + the executor run on a RHEL 9.2 worker (no such host / agent here) — `deploy/install.sh` is
shellcheck-verified but not yet run on a live worker.

## Core Web Vitals (MKP 1.2.0)

The 1.2.0 package adds Core Web Vitals support: LCP, CLS, INP, FCP, and TTFB are captured per
journey via a vendored `web-vitals` v4 IIFE injected at page load, surfaced as `synmon_journey`
perfdata, graphed, and guarded by new WATO threshold rulesets for LCP, CLS, and INP.

**Build confirmed:** `make mkp` produces `dist/synmon-1.2.0.mkp` (11 `cmk_addons_plugins` files +
1 `agents` file, same packaging structure as 1.1.0 — only the version string and the wiring modules
changed).

**Verified live on 2.4.0p32.cce:**

```text
$ mkp add /tmp/synmon-1.2.0.mkp && mkp enable synmon 1.2.0
$ mkp list | grep synmon
synmon 1.2.0  Synthetic Monitoring (Playwright)  Synthetic Monitoring  2.4.0p32  None  12  Enabled (active on this site)
$ python3 -c "import …graphing.synmon as g, …rulesets.synmon_journey as rj; …"
web-vitals metrics registered: ['metric_synmon_cls', 'metric_synmon_fcp', 'metric_synmon_inp', 'metric_synmon_lcp', 'metric_synmon_ttfb']
web-vitals graph: synmon_web_vitals
lcp perfometer  : synmon_lcp
journey ruleset : synmon_journey
ALL CWV WIRING IMPORTS OK
```

Confirms the five new `Metric` objects, the `Graph`/`Perfometer`, and the journey ruleset's new
`SimpleLevels` (TimeSpan for LCP/INP, `Float` for CLS) all construct against the real 2.4 API.
**Deferred (unchanged from Plans 2–3):** live service discovery + a real browser run capturing
actual vitals on a RHEL 9.2 worker.

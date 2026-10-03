# CLAUDE.md — Checkmk Synthetic Monitoring

Custom synthetic monitoring for **Checkmk 2.4 CCE and 2.5 Ultimate** (air-gapped, Playwright), as an
alternative to the commercial Synthetic Monitoring (Robotmk) add-on. No Robot Framework / RCC / built-in Synthetic
Monitoring dependency. Scope is **web-application user-journey monitoring only** (no SAP GUI /
fat-client monitoring).

## Architecture (decided)

- Dedicated **RHEL 9.2+ Linux workers** per network segment run Playwright journeys; each worker
  is monitored by the **remote site that owns its segment** (agent over TLS, port 8000).
- **Asynchronous**: a systemd/Quadlet timer runs the executor (separate container), which writes
  result JSON to a **spool dir**. The agent plugin only **reads** the spool — it never launches a
  browser (agent calls are synchronous and would time out).
- Results map to **logical target hosts** via **piggyback** (`<<<<target_host>>>>`); worker +
  its targets are co-located on the same remote site so piggyback stays local.
- **Web-only, Playwright (Linux).** The executor sits behind one normalized JSON contract; keep
  `synmon_contract` + the section format free of any Playwright/OS coupling — for clean separation
  and offline testability (and a future browser-engine swap), not for any non-web client.

### Three-plan build
1. **Worker producer subsystem — DONE** (this repo's current code): contract, executor, agent plugin.
2. **Server-side MKP — DONE** (`checkmk_mkp/`): `synmon_journey`/`synmon_worker` agent_based checks,
   graphing, WATO rulesets, checkman, manifest + the stdlib `.mkp` builder. Written against the
   verified signatures in `docs/checkmk-2.4-api-verification.md`.
3. **Scheduler + bakery deployment — DONE**: hardened Podman Quadlet executor unit + timer and an
   idempotent `deploy/install.sh`; Agent Bakery plugin + `AgentConfig` ruleset that deploy the agent
   plugin. Live validation on a RHEL 9.2 worker is pending (no host available).

## Repo layout
- `contract/` — `synmon_contract` Pydantic models (the contract) + `schema_export`. **No Playwright/OS imports.**
- `schema/` — generated, committed JSON Schema (`synmon_result`, `synmon_worker`). Regenerate with `make schema`; CI fails on drift.
- `executor/` — `synmon_executor` (Playwright). `core.py` is browser-agnostic (drives a `Session` Protocol); `playwright_session.py` is the only real-browser code and imports `playwright` **lazily**. Two image variants, both installing only from `wheelhouse/` (built by `scripts/build_wheelhouse.sh`
  with `uv.lock` hashes): `Containerfile` = **default, Red Hat UBI 9 minimal** (Python 3.12 +
  browser libs from UBI repos; only Playwright's headless-shell Chromium copied from the Playwright
  image; entrypoint `python3.12` since `python3` is 3.9), `Containerfile.playwright` = official
  Playwright **noble** image (Playwright-supported). Red Hat Hardened Images lack Chromium's libs.
- `agent_plugin/synmon_collector.py` — Checkmk agent plugin, **standard library only** (runs on the worker).
- `checkmk_mkp/` — the MKP staging tree. `cmk_addons/plugins/synmon/lib/` (`parsing.py`,
  `evaluate.py`) is **stdlib-only** decision logic, unit-tested offline (`tests/server/`).
  `agent_based/`, `graphing/`, `rulesets/` are thin `cmk.*` wiring. The Agent Bakery plugin (API v1)
  lives in the `lib` part, `lib/python3/cmk/base/cee/plugins/bakery/synmon.py` — v1 plug-ins are
  **only** loaded from `cmk.base.cee.plugins.bakery` (2.4 and 2.5), never from `cmk_addons`.
  `tests/checkmk/` proves every plug-in is found by Checkmk's own loaders inside real 2.4/2.5
  images. `agents/plugins/synmon_collector.py` is the baked agent plugin (kept byte-identical to
  `agent_plugin/`, guarded by a test). `manifest.json` lists the packaged files.
  **No `__init__.py` under `cmk_addons/`** (PEP-420 namespace packages).
- `deploy/` — worker provisioning: hardened Podman Quadlet `synmon-executor.{container,timer}`
  templates (non-root, read-only, caps dropped, memory/pids capped via `PodmanArgs=`) + idempotent
  `install.sh` (validates every value before sed-rendering the units; `--agent-user` adds the
  agent user to the `synmon` group).
- `scripts/build_mkp.py` — stdlib-only `.mkp` builder (reproduces the verified package format; no site needed).
  `--set-version X.Y.Z` rewrites only the manifest's top-level `"version"` line (used by the release job).
  `scripts/check_commits.py` — stdlib-only Conventional Commits check (PR CI + `make hooks`).
  `scripts/build_wheelhouse.sh` / `scripts/test_image.sh` — executor image inputs + hardened image smoke test.
- `tests/` — cross-cutting (smoke + end-to-end contract flow); `tests/server/` covers the MKP lib + the build.
- `.devcontainer/` — dev image (+ pre-commit cache) + Checkmk 2.5 Ultimate service. `.gitlab-ci.yml` — air-gapped CI.
  `.github/workflows/` — `ci.yml` (lint, secrets, tests, Checkmk matrix, live browser, both
  images, then `release` on `main` and `dependabot-merge` on Dependabot PRs, both gated by
  `needs:` on every other job) + `commits.yml` (Conventional Commits check of the PR title and
  every PR commit; also on title edits).
  `.github/dependabot.yml` — weekly grouped updates with `build(deps)` / `ci(deps)` subjects (they
  never release); uv / pre-commit minor+patch are merged by `dependabot-merge` after a 7-day
  cooldown. The `Main` ruleset only blocks deletion + force-push — no required checks or approvals
  (Actions may not approve PRs). The commit check stays **advisory** on purpose: a required check
  would also reject the release job's push to `main`, and the GitHub Actions app cannot be a
  ruleset bypass actor on this personal repo.
  All actions are pinned by commit SHA (+ `# vX.Y.Z` comment) — keep new ones pinned too.

## Releases (automated — never bump the version by hand)
On every push to `main` the CI `release` job runs python-semantic-release (pinned in the uv
`release` group, hash-locked; config in `pyproject.toml` `[tool.semantic_release]`). From the commit
subjects since the last `v*` tag: `feat` → minor, `fix`/`perf` → patch, `!`/`BREAKING CHANGE:` →
major, anything else → no release. It stamps `checkmk_mkp/manifest.json` via `build_command`, commits
`chore(release): vX.Y.Z` as `github-actions[bot]`, tags and creates the GitHub Release; a final step
attaches `synmon-X.Y.Z.mkp` (idempotent — re-run the job to recover). Squash merges use the PR
title, so **the PR title decides the release**. Pitfalls already hit: semantic-release's
`version_variables` also rewrites `"version.min_required"` in JSON, and its `assets` are uploaded to
the release — use neither. Never hard-code the MKP version in tests (read the manifest).

## Result contract (v1.0.0 — the keystone)
One atomically-written JSON file per `(target_host, journey)` in the spool. Source of truth =
`contract/src/synmon_contract/models.py` (`JourneyResult`, `Heartbeat`, `WorkerHealth`). Key fields:
`schema_version, executor, worker_id, target_host, journey_name, journey_id, status (0–3),
summary, started_at (epoch, drives staleness), duration_ms, max_age_s, steps[], artifacts, error`.
`target_host` must match `TARGET_HOST_PATTERN` (Checkmk host-name characters only — it becomes a
piggyback header). The executor also writes `heartbeat.json` (`run_error` set when a whole run
failed → worker service CRIT); the agent plugin combines it with a spool scan into the
`synmon_worker` self-health section.

## Conventions
- **Status integers**: `0 OK / 1 WARN / 2 CRIT / 3 UNKNOWN` everywhere.
- **Section names**: `synmon_journey`, `synmon_worker` (both `sep(0)`). Plugin family: `synmon`.
- **Agent output order**: `<<<synmon_worker:sep(0)>>>` first (non-piggyback), then per target_host
  in **sorted** order: `<<<<host>>>>` + `<<<synmon_journey:sep(0)>>>` + one JSON line per journey
  (sorted) + `<<<<>>>>`. This order is a contract the server-side parser will rely on.
- **Paths** (override via `SYNMON_*` env): spool `/var/lib/synmon/spool`, artifacts
  `/var/lib/synmon/artifacts`, heartbeat `/var/lib/synmon/heartbeat.json`. Run by an unprivileged
  `synmon` user; group-readable by the agent.
- **Atomic writes**: temp → `fsync` → `os.replace`. Single-writer assumption (sequential journeys
  + systemd serializes runs); a shared spool dir would need unique temp suffixes.
- **Secrets**: journey credentials come from the environment / podman secrets — never inline or baked.
  Playwright traces record typed passwords and cookies, so they are opt-in (`SYNMON_TRACE=1`);
  failure screenshots are `<target_host>__<journey_id>.png`, mode `0640`, pruned after
  `SYNMON_ARTIFACT_MAX_AGE_S` (7 days).
- **Spool is untrusted input** for the root agent plugin (Chromium runs without its sandbox and the
  container can write `/var/lib/synmon`): the collector opens the spool dir with `O_NOFOLLOW` and
  reads entries via `dir_fd`, only regular files (no FIFOs, ≤ 1 MiB, ≤ 500 files / 16 MiB total),
  and drops results with an invalid `target_host` or one missing from the root-owned
  `/etc/synmon/allowed_hosts` (`install.sh --allowed-hosts`; absent file → worker WARN, unreadable
  → fail closed). Counts go to `synmon_worker` (`unparseable`, `not_allowed`, `overflow`,
  `allowlist`). Discovery rejects invalid hosts
  and colliding `(host, journey_id)` / `(host, name)` as load errors. Results of removed journeys are
  pruned from the spool (not in a run with load errors).
- **Commits**: Conventional Commits (`<type>[(scope)][!]: <description>`, ≤ 100 chars) — they drive
  releases (see Releases).
- **Air-gap**: pin all versions (Playwright 1.63.0, Python 3.12, uv 0.5.11, Checkmk 2.4.0p32);
  no runtime internet; browsers vendored in the image (`PLAYWRIGHT_BROWSERS_PATH`). Executor base
  images are pinned by digest (`ARG` defaults + `Makefile`); CI installs only from `uv.lock` hashes.
  The dev container's uv 0.5.11 rewrites `uv.lock` in an older format — change the lock with a
  current uv image (e.g. `ghcr.io/astral-sh/uv:python3.12-bookworm-slim`), not `make`.

## Verified Checkmk 2.4 API (from `docs/checkmk-2.4-api-verification.md`)
Canonical plugin base = `local_cmk_addons_plugins_dir` =
`local/lib/python3/cmk_addons/plugins/<pkg>/{agent_based,graphing,rulesets,checkman}`.
Imports: `cmk.agent_based.v2`, `cmk.rulesets.v1` (+ `form_specs`, `rule_specs`), `cmk.graphing.v1`,
bakery `cmk.base.plugins.bakery.bakery_api.v1` — installed to
`local/lib/python3/cmk/base/cee/plugins/bakery/` (the `cmk_addons/.../bakery/` dir is only scanned
for bakery API **v2** in 2.5+; v1 is removed in 2.7, see Werk #18600). Do **not** use the legacy
`local/lib/check_mk/base/plugins/agent_based` dir for v2 plugins.

## Build / test / lint (ALL inside the dev container — never on the host)
- `make test` — full pytest suite.
- `make lint` — pre-commit hooks from `.pre-commit-config.yaml` (gitleaks, hygiene, ruff,
  shellcheck with `.shellcheckrc` `enable=all`, hadolint, actionlint — identical to the CI `lint`
  job) + `mypy` (scoped to `contract/src`, `executor/src`, the MKP `lib/`, and `scripts/`).
  `make typecheck` = mypy only; `make secrets` = gitleaks over the full history.
- `make test-checkmk` — plug-in loading tests + MKP `lib/` tests with the real Checkmk libraries
  (runs `tests/checkmk/run-pytest.sh` inside `CHECKMK_IMAGE`, default the 2.5 Ultimate image;
  first exports the hashed test requirements to `.cache/`, since the image has no uv).
- `make format` — apply `ruff format`.
- `make schema` — regenerate the committed JSON Schema.
- `make mkp` — build `dist/synmon-<version>.mkp` (stdlib builder; no Checkmk site needed).
- `make hooks` — install the `commit-msg` hook (host `python3`, stdlib only — nothing installed).
- `make wheelhouse` / `make image` / `make image-test` (`VARIANT=ubi9|playwright`) — executor image: collect wheels (network),
  build offline, run hardened against the mock site (`scripts/test_image.sh`). Guide: `deploy/README.md`.
- `make checkmk-up` / `make checkmk-down` — the Checkmk 2.5 Ultimate service (unstable under amd64
  emulation on macOS; fine for read-only API inspection, exits ~60–90s).
- Tests are **network-free**; the real browser is only used behind `SYNMON_INTEGRATION`
  (`tests/integration/`, run by `make integration` and the CI `live browser integration` job).
- pre-commit's `--all-files` skips **untracked** files: `git add` new files before `make lint`.

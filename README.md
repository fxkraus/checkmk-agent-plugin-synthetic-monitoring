# Checkmk Synthetic Monitoring (Playwright, air-gapped)

Custom synthetic monitoring for **Checkmk 2.4 CCE and 2.5 Ultimate** — a self-hosted, Playwright-based
alternative to Checkmk's commercial Synthetic Monitoring (Robotmk) add-on. Dedicated Linux workers run Playwright journeys on a timer,
write results to a spool directory, and a Checkmk agent plugin turns them into piggyback services
on logical target hosts. It does robust, modern **user-journey monitoring for web applications**
with Playwright on Linux; the executor sits behind a normalized JSON contract for clean separation
and offline testability.

> Status: the worker producer subsystem, the server-side MKP, and the Quadlet scheduler + Agent
> Bakery deployment are complete. Live execution on a RHEL 9.2 worker is the remaining real-world
> validation. See `CLAUDE.md` for the architecture.

## What's here

| Path | Purpose |
|---|---|
| `contract/` | `synmon_contract` — the normalized result contract (Pydantic). No Playwright/OS imports. |
| `schema/` | Generated + committed JSON Schema (CI fails on drift). |
| `executor/` | `synmon_executor` — Playwright executor: authoring SDK, browser-agnostic runner, atomic spool + heartbeat, pinned air-gapped images: `Containerfile` (Red Hat UBI 9, default) and `Containerfile.playwright` (Playwright-supported Ubuntu). |
| `agent_plugin/` | `synmon_collector.py` — stdlib-only Checkmk agent plugin (spool → sections). |
| `checkmk_mkp/` | The MKP: server-side `cmk_addons/plugins/synmon/{lib,agent_based,graphing,rulesets,checkman}`, the Agent Bakery plugin (`lib/python3/cmk/base/cee/plugins/bakery/`), and the baked agent plugin (`agents/`) + `manifest.json`. The stdlib-only `lib/` is unit-tested offline; `tests/checkmk/` loads every plug-in with Checkmk's own loaders inside real 2.4 and 2.5 images. |
| `deploy/` | Worker provisioning: hardened Podman Quadlet executor unit + timer and an idempotent `install.sh`. |
| `scripts/build_mkp.py` | Site-free, stdlib-only `.mkp` builder (used by `make mkp` and CI). |
| `tests/` | Smoke + end-to-end contract test; `tests/server/` covers the MKP `lib/` and the package build. |
| `.devcontainer/`, `.gitlab-ci.yml`, `.github/workflows/` | Dev container (incl. Checkmk CCE 2.4), air-gapped GitLab CI, and GitHub Actions (CI + release). |
| `docs/` | Design spec, implementation plans, and the verified Checkmk 2.4 API reference. |

## Writing a journey

Journeys are Python modules discovered from a directory. They never touch contract plumbing:

```python
from synmon_executor import journey


@journey(name="login", target_host="app.example.com", max_age_s=900, interval_s=300)
async def run(page, ctx):
    async with ctx.step("open login"):
        await page.goto("https://app.example.com/login")
    # credentials come from the environment, never inline
```

A `@login(target_host=...)` runs before that host's journeys and hands them its session state;
each target host can have at most one. Invalid decorator arguments (negative `retries`,
`max_age_s` or `interval_s`, `timeout_s <= 0`) and a second login for the same host are reported
as load errors on the worker service instead of running.

## Web performance

Core Web Vitals (LCP, CLS, INP) and additional timing metrics (FCP, TTFB) are captured
automatically per journey and surfaced as perfdata with configurable thresholds in the
`synmon_journey` check — no extra authoring required.

- **LCP, FCP, TTFB** are available on every navigation-only journey.
- **CLS and INP** require the journey to scroll or interact with the page; navigation-only journeys
  report `None` for these two metrics (they are omitted from perfdata rather than graphed as zero).

Graphs and threshold rulesets for LCP, CLS, and INP are included in the MKP under
*Synthetic monitoring* in WATO.

## SLOs with Checkmk availability / SLA

Checkmk has no metric-based SLO engine; *Availability* (all editions) and *SLA* (commercial
editions) are computed from each service's **state history**. So each `Journey …` service's state
is the SLI, and the check is built to keep that state honest:

- **Fixed cadence** — the timer runs on the clock (`OnCalendar`), so every result covers the same
  slice of time and "% of time OK" equals "% of successful runs".
- **Retries don't hide failures** — a pass that needed a retry is WARN by default
  (*State when the journey succeeded only after a retry*).
- **Latency is part of the SLI** — total/per-step duration and Web Vitals thresholds turn the
  service WARN/CRIT.
- **No measurement ≠ outage** — a stale result is UNKNOWN by default, and so are journeys skipped or
  cut short because the run budget was exhausted (a retry cut short keeps the failure already
  seen), journeys whose executor crashed, and journeys whose target host's `@login` failed (the
  outage is reported once, on the login service). Configure your availability/SLA views to
  exclude (or separately report) UNKNOWN, and watch the *Synthetic Worker Scheduler* service for
  the cause: it turns CRIT with the error when a whole run fails (e.g. the browser cannot start),
  and WARN/CRIT when its heartbeat is older than 10/30 min (default, also without a rule) — e.g.
  the timer stopped or the container never started.
- **Timestamps must be trustworthy** — a result without a valid `started_at` counts as stale, and
  one more than 60 s in the future turns the service WARN. Keep worker clocks NTP-synced with the
  Checkmk server.
- **Removed journeys disappear** — results of journeys that no longer exist are deleted from the
  spool, so their services report "item not found" instead of staying stale forever.

Failure screenshots are kept 7 days; Playwright traces are off by default because they record
typed passwords and session cookies (see [`deploy/README.md`](deploy/README.md)).

Set the piggyback rule *Processing of piggybacked host data* to keep data valid for at least the
schedule interval plus one check interval, or journeys flap stale between runs.

## Development

Everything runs **inside the dev container** (Docker required):

```sh
make test          # full pytest suite (network-free)
make lint          # pre-commit hooks (same as CI) + mypy
make typecheck     # mypy only
make secrets       # gitleaks over the full git history
make format        # apply ruff formatting
make schema        # regenerate the committed JSON Schema
make mkp           # build dist/synmon-<version>.mkp
make hooks         # install the commit-msg hook (Conventional Commits check)
make test-checkmk  # plug-in loading tests inside a real Checkmk image
                   # (CHECKMK_IMAGE=checkmk/check-mk-cloud:2.4.0-latest for 2.4)
make wheelhouse    # collect the offline inputs for the executor image (needs network)
make image         # build the executor image from ./wheelhouse: UBI 9 by default,
                   # VARIANT=playwright for the Playwright-supported Ubuntu image
make image-test    # run the image hardened against the mock site (same VARIANT)
```

`make lint` runs the hooks from `.pre-commit-config.yaml`: gitleaks, file hygiene, ruff,
shellcheck, hadolint and actionlint. To run them on every commit, install the git hook inside the
dev container (`uv run pre-commit install`) — or simply run `make lint` before pushing.

See `CLAUDE.md` for the result-contract schema, naming/section conventions, paths, and the
verified Checkmk 2.4 plugin API import paths.

## Server-side MKP

`make mkp` builds `dist/synmon-<version>.mkp` with `scripts/build_mkp.py` — a standard-library-only
builder that reproduces the verified `.mkp` on-disk format (see
`docs/checkmk-2.4-api-verification.md`), so it needs **no running Checkmk site**. Install it on a
2.4 site:

```sh
mkp add synmon-1.0.0.mkp
mkp enable synmon 1.0.0
```

It registers the `synmon_journey` (one service per journey) and `synmon_worker` (scheduler health)
checks, their graphs/perfometer, the WATO rulesets under *Synthetic monitoring*, and an Agent
Bakery rule that deploys the agent plugin to worker hosts. Bump the version in
`checkmk_mkp/manifest.json` before releasing a new package.

## Worker deployment

Two layers provision a worker:

- **Agent plugin** — deployed by the **Agent Bakery** (rule *Synthetic monitoring: agent
  deployment*), or manually from the MKP's `agents/plugins/synmon_collector.py`.
- **Executor** — a hardened Podman **Quadlet** container on a systemd **timer**, installed by
  `deploy/install.sh` (creates the unprivileged `synmon` user + state dirs, renders the units,
  enables the timer). The executor image is based on Red Hat UBI 9 by default (a
  Playwright-supported Ubuntu variant is available too) and installs the executor offline from a
  hashed wheelhouse (`make wheelhouse`, then `make image`). See `deploy/README.md` for building the image and
  installing it. Live validation on a real RHEL 9.2 worker is pending.

## CI / releases (GitHub Actions)

- **CI** (`.github/workflows/ci.yml`) runs on every push to `main`, every PR, and on demand
  (*Run workflow*). Jobs:
  - `lint` — the pre-commit hooks (identical to `make lint` minus mypy);
  - `secrets` — gitleaks over the pushed / PR commits;
  - `typecheck + test + package` — mypy, the offline suite, schema drift, `make mkp` (on `main`
    the `.mkp` is kept as a build artifact for 90 days);
  - `pytest (Checkmk 2.4)` / `pytest (Checkmk 2.5)` — `tests/checkmk/` inside the real Checkmk
    images (`-latest` tags, so new patch releases are picked up automatically);
  - `live browser integration` — Playwright against the mock site;
  - `executor image (ubi9)` / `executor image (playwright)` — builds each image variant from the
    wheelhouse and runs it hardened against the mock site (`make wheelhouse image image-test`).

  All actions are pinned by commit SHA.
- **Dependabot** (`.github/dependabot.yml`) opens weekly, grouped minor/patch PRs for uv,
  pre-commit, GitHub Actions and the dev-container image. uv and pre-commit minor/patch updates
  are squash-merged by CI's `dependabot-merge` job once every other job passed;
  Actions, Docker and all major updates wait for a manual review. (The merge is gated with
  `needs:` inside CI rather than GitHub auto-merge, so it does not depend on a branch ruleset
  requiring these checks.)
- **Conventional commits** (`.github/workflows/commits.yml`) checks the PR title and every commit
  subject of a pull request with `scripts/check_commits.py` (also on title edits).
- **Release** — the `release` job in CI runs on every push to `main` once all other jobs passed.
  [python-semantic-release](https://python-semantic-release.readthedocs.io/) (pinned in the
  `release` dependency group, hash-locked in `uv.lock`) derives the next version from the commit
  subjects since the last `v*` tag, writes it to `checkmk_mkp/manifest.json`, builds the MKP,
  commits `chore(release): vX.Y.Z`, tags it and publishes a GitHub Release with the `.mkp`
  attached. A failed release is recovered by re-running the job.

## Commit messages and versioning

Commit subjects (and PR titles, which become the subject of a squash merge) follow
[Conventional Commits](https://www.conventionalcommits.org/): `<type>[(scope)][!]: <description>`,
at most 100 characters. They decide the next MKP version:

| Subject | Release |
|---|---|
| `feat(executor): per-step screenshots` | minor (`1.2.0` → `1.3.0`) |
| `fix: …` / `perf: …` | patch (`1.2.0` → `1.2.1`) |
| `feat!: …` / `fix(api)!: …`, or a `BREAKING CHANGE:` footer | major (`1.2.0` → `2.0.0`) |
| `build`, `chore`, `ci`, `docs`, `refactor`, `revert`, `style`, `test` | none |

Dependabot uses `build(deps)` / `ci(deps)`, so dependency updates never release on their own.
`make hooks` installs a `commit-msg` hook that runs the same check locally.

## Security

See [`SECURITY.md`](SECURITY.md) for how to report a vulnerability.

## License

[MIT](LICENSE) © Felix Kraus. The vendored `web-vitals` library
(`executor/src/synmon_executor/vendor/`) is © Google LLC under the Apache License 2.0 — see
[`LICENSE-web-vitals`](executor/src/synmon_executor/vendor/LICENSE-web-vitals).

Checkmk and Robotmk are trademarks of their respective owners. This is an independent project,
not affiliated with or endorsed by Checkmk GmbH or the Robotmk project.

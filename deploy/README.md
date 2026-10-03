# Worker deployment (executor scheduler)

Provisions the synthetic-monitoring **executor** on a RHEL 9.2+ worker as a hardened Podman
**Quadlet** container driven by a systemd **timer**. The Checkmk **agent plugin** is deployed
separately by the Agent Bakery (see the `synmon` MKP) — this directory only sets up the executor.

| File | Purpose |
|---|---|
| `synmon-executor.container` | Quadlet unit template for the executor container (hardened: non-root, read-only rootfs, all caps dropped, no ports). |
| `synmon-executor.timer` | systemd timer template that runs the executor on a schedule. |
| `executor.env.example` | Non-secret config (worker id); copied to `/etc/synmon/executor.env`. |
| `install.sh` | Idempotent installer: creates the `synmon` user + state dirs, renders the units, enables the timer. |

## Build the executor image

There are two variants. Both install the executor the same way and pass the same tests:

| `VARIANT` | Containerfile | Base | Size (unpacked) | Use when |
|---|---|---|---|---|
| `ubi9` (default) | `executor/Containerfile` | Red Hat **UBI 9** minimal | ~780 MB | You need a Red Hat base image: OS, Python 3.12 and every browser library come from Red Hat's UBI 9 repos. |
| `playwright` | `executor/Containerfile.playwright` | Official Playwright image (Ubuntu 24.04) | ~2.7 GB | You want the platform Playwright officially supports. |

What to know about `ubi9`:
- **The browser is not from Red Hat.** RHEL does not ship Chromium. The image copies Playwright's
  pinned headless-shell Chromium out of the official Playwright image, the same binary the
  `playwright` variant runs, and leaves the full browsers behind. The executor always runs headless,
  so the headless shell is all it needs.
- **Playwright does not officially support RHEL.** Both variants run the same hardened
  end-to-end test in CI, so a Playwright upgrade that breaks UBI 9 is caught before release.
- Red Hat Hardened Images (images.redhat.com) are not an option yet: their package repository lacks
  about a third of the libraries Chromium needs (`atk`, `at-spi2`, `mesa-libgbm`, `libdrm`,
  `libXdamage`, `libXfixes`, `libXrandr`, `libwayland-server`).

Both variants install the executor **offline** from a *wheelhouse*: the two project wheels, every
third-party wheel pinned in `uv.lock`, and a `requirements.txt` with the lock's sha256 hashes. `pip`
never touches a package index, and `--require-hashes` rejects any wheel that does not match the
lock.

**1. Connected machine: collect the inputs** (Docker required, like every `make` target):

```sh
make wheelhouse                                   # -> ./wheelhouse (WHEEL_ARCH=aarch64 for arm64)
podman pull mcr.microsoft.com/playwright/python:v1.63.0-noble
podman pull registry.access.redhat.com/ubi9/ubi-minimal:latest     # ubi9 variant only
podman save -o base-images.tar mcr.microsoft.com/playwright/python:v1.63.0-noble \
  registry.access.redhat.com/ubi9/ubi-minimal:latest
```

Carry `wheelhouse/` and `base-images.tar` across the air gap, or push the base images to the
internal registry mirror. The Playwright image tag must match the `playwright` pin in
`executor/pyproject.toml`. Use its **noble** variant (Ubuntu 24.04, Python 3.12): jammy ships
Python 3.10, which the executor does not support.

The `ubi9` build also installs RPMs, so it needs a UBI 9 repository. Either build it on the
connected side and carry the finished image across (`podman save` / `podman load`), or point the
build host at an internal mirror of the UBI 9 BaseOS and AppStream repos, for example Satellite or
Nexus.

**2. Build** from a checkout of this repo with `wheelhouse/` in its root:

```sh
podman load -i base-images.tar                    # or reference the internal mirror instead
make image CONTAINER=podman \
  BASE_IMAGE=registry.internal.example/mirror/ubi9/ubi-minimal@sha256:<digest> \
  PLAYWRIGHT_IMAGE=registry.internal.example/mirror/playwright/python@sha256:<digest> \
  EXECUTOR_IMAGE=registry.internal.example/synmon/executor:1.0.0
# Playwright-supported variant: add VARIANT=playwright (BASE_IMAGE is then unused)
```

This is equivalent to `podman build --platform linux/amd64 --build-arg BASE_IMAGE=...
--build-arg PLAYWRIGHT_IMAGE=... -f executor/Containerfile -t ... .`. The build context is the repo
root, but `.dockerignore` only admits `wheelhouse/`.

**3. Test it**, still offline apart from the mock-site image `python:3.12-slim-bookworm`:

```sh
make image-test CONTAINER=podman EXECUTOR_IMAGE=registry.internal.example/synmon/executor:1.0.0
```

This runs the image the way the Quadlet unit does: unprivileged, with a read-only rootfs, all
capabilities dropped and a tmpfs `/tmp`. It runs the integration journeys against the mock site and
checks the spool, the heartbeat and the captured Web Vitals. CI runs steps 1–3 for both variants
on every push.

**4. Publish** the image to the internal registry and note its digest for `install.sh --image`:

```sh
podman push registry.internal.example/synmon/executor:1.0.0
podman image inspect --format '{{.Digest}}' registry.internal.example/synmon/executor:1.0.0
```

## Prerequisites (air-gapped)

1. **Load the executor image** on the worker from the internal registry, referenced **by digest**
   (built as above):
   ```sh
   podman pull registry.internal.example/synmon/executor@sha256:<digest>
   ```
2. **Podman 4.4+** (Quadlet support) and **systemd** (both stock on RHEL 9.2).

## Install

```sh
sudo ./install.sh \
  --image registry.internal.example/synmon/executor@sha256:<digest> \
  --worker-id worker01 \
  --schedule '*:0/5' \
  --journeys /etc/synmon/journeys \
  --allowed-hosts app.example.com,shop.example.com
```

All flags have `SYNMON_*` env equivalents. The script is idempotent — re-run it to update the
image digest, schedule or allowed hosts. It refuses the placeholder image, warns if the image is
not pinned by digest or not loaded yet, and (re)sets the journeys dir to `root:synmon 0750`.

`--allowed-hosts` writes `/etc/synmon/allowed_hosts` (root-owned, one host per line, `#`
comments): the agent plugin forwards only results for these target hosts and counts the rest on
the worker service. Without the file every valid host name is forwarded and the worker service is
WARN ("no target-host allowlist"). If the file exists but cannot be read safely (e.g. it is a
symlink), nothing is forwarded.

`--schedule` is a systemd `OnCalendar` expression (default `*:0/5`, every 5 minutes on the
clock). A fixed cadence — rather than "N minutes after the last run" — means each result covers
the same slice of time, so Checkmk availability/SLA percentages equal the share of successful
runs. Keep `SYNMON_RUN_BUDGET_S` in `/etc/synmon/executor.env` below the interval: journeys that
cannot start within the budget are reported UNKNOWN ("skipped") and the worker service turns WARN;
a journey cut short by the budget (not by its own timeout) is UNKNOWN too, never CRIT,
instead of the whole run being killed by systemd and every service going stale.

The executor validates every `SYNMON_*` variable before it starts the browser. An invalid value
(e.g. `SYNMON_RETRIES=-1` or `SYNMON_TIMEOUT_S=0`) aborts the run with a heartbeat whose error
names the variable, so the worker service goes CRIT instead of silently going stale.

## Journeys and secrets

- Drop journey modules into the journeys dir (default `/etc/synmon/journeys`) as `root:synmon`
  mode `0640`; they are mounted read-only at `/journeys` in the container. They are code, so the
  `synmon` runtime user must not be able to change them.
- Provide journey credentials as **podman secrets**, never in the env file or the image:
  ```sh
  printf '%s' "$APP_PASSWORD" | sudo podman secret create synmon-app-password -
  ```
  then uncomment the matching `Secret=` line in `/etc/containers/systemd/synmon-executor.container`
  and `sudo systemctl daemon-reload`.

## Verify

```sh
systemctl status synmon-executor.timer
sudo systemctl start synmon-executor.service     # run once now
ls -l /var/lib/synmon/spool /var/lib/synmon/heartbeat.json
```

The agent plugin (baked onto the same host) turns the spool into `synmon_journey` /
`synmon_worker` sections. The spool is owned `synmon:synmon`, group-readable; if the agent runs
as an unprivileged user (e.g. `cmk-agent`), pass `--agent-user <user>` to add it to the `synmon`
group so it can read the spool.

> The executor runs unprivileged with a read-only rootfs and all Linux capabilities dropped; only
> `/tmp` (tmpfs) and `/var/lib/synmon` are writable. It is capped at 2 GiB of memory (no extra
> swap) and 1024 processes (`PodmanArgs=` in the unit). Egress to journey targets uses the
> default Podman network; no ports are published.
>
> By default Playwright starts Chromium **without its sandbox**, so this container is the only
> isolation from the monitored pages (see *Chromium sandbox* below to add Chromium's own). Either
> way, treat `/var/lib/synmon` as untrusted input: the agent plugin (root)
> does not follow a symlinked spool directory, only reads regular files (no symlinks/FIFOs, max
> 1 MiB each, at most 500 files / 16 MiB per call), drops results whose `target_host` is not a
> plain host name or not in `/etc/synmon/allowed_hosts`, and reports all of it on the worker
> service.

## Chromium sandbox

`install.sh --chromium-sandbox` adds Chromium's own sandbox as a second layer inside the
container: a compromised renderer is then also confined by Chromium's user-namespace sandbox,
not only by the container. It renders two extra lines into the unit:

- `Environment=SYNMON_CHROMIUM_SANDBOX=1` — Playwright launches Chromium with
  `chromium_sandbox=True`.
- `AddCapability=SYS_CHROOT` — the sandbox `chroot()`s into an empty directory, which Podman's
  seccomp profile only permits when `CAP_SYS_CHROOT` is in the container's bounding set. The
  executor itself still runs with no effective, permitted or ambient capabilities
  (unprivileged user, `NoNewPrivileges`); only the sandbox's fresh user namespace uses it.

It needs unprivileged user namespaces (on by default on RHEL 9: `user.max_user_namespaces`) and
a seccomp profile that allows `unshare`: Podman's RHEL 9 default does, Docker's default does not.
CI runs the hardened image with the sandbox under the RHEL 9 Podman seccomp profile (taken from
the `containers-common` package of AlmaLinux 9). **Not yet verified on a RHEL 9.2 host with
SELinux enforcing** — enable it on one worker first: if the sandbox cannot start, every run fails
and the *Synthetic Worker Scheduler* service turns CRIT with "Chromium sandboxing failed"; re-run
`install.sh` without the flag to go back.

## Failure artifacts and retention

A failed journey leaves a full-page screenshot in `/var/lib/synmon/artifacts`, named
`<target_host>__<journey_id>.png` (mode `0640`). Artifacts older than
`SYNMON_ARTIFACT_MAX_AGE_S` (default 7 days) are deleted at the start of each run.

Playwright **traces are off by default**: a trace records every typed value (including
passwords) and the request headers and bodies (session cookies). To debug a journey, set
`SYNMON_TRACE=1` in `/etc/synmon/executor.env` temporarily; failures then also write
`<target_host>__<journey_id>.trace.zip`. Unset it and delete the traces afterwards.

Results of journeys that no longer exist (removed or renamed) are deleted from the spool at the
end of a run, unless a journey file failed to load in that run.

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

## Prerequisites (air-gapped)

1. **Mirror + load the executor image** from the internal registry, referenced **by digest**:
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
  --journeys /etc/synmon/journeys
```

All flags have `SYNMON_*` env equivalents. The script is idempotent — re-run it to update the
image digest or schedule.

`--schedule` is a systemd `OnCalendar` expression (default `*:0/5`, every 5 minutes on the
clock). A fixed cadence — rather than "N minutes after the last run" — means each result covers
the same slice of time, so Checkmk availability/SLA percentages equal the share of successful
runs. Keep `SYNMON_RUN_BUDGET_S` in `/etc/synmon/executor.env` below the interval: journeys that
cannot start within the budget are reported UNKNOWN ("skipped") and the worker service turns WARN,
instead of the whole run being killed by systemd and every service going stale.

## Journeys and secrets

- Drop journey modules into the journeys dir (default `/etc/synmon/journeys`); they are mounted
  read-only at `/journeys` in the container.
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
unprivileged, pass `--agent-group <group>` so it can read the spool.

> The executor runs unprivileged with a read-only rootfs and all Linux capabilities dropped; only
> `/tmp` (tmpfs) and `/var/lib/synmon` are writable. Egress to journey targets uses the default
> Podman network; no ports are published.

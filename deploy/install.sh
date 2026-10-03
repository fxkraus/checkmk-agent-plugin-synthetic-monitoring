#!/usr/bin/env bash
# Idempotent installer for the synthetic-monitoring executor on a RHEL 9.2+ worker.
#
# Provisions an unprivileged `synmon` user + state directories, renders the hardened Quadlet
# units, and enables the timer. Safe to re-run. Must run as root. Configure via flags or the
# matching SYNMON_* environment variables.
#
# Usage: sudo ./install.sh [--image REF] [--worker-id ID] [--schedule '*:0/5']
#                          [--journeys DIR] [--agent-user USER]
#                          [--allowed-hosts host1,host2,...] [--chromium-sandbox]
#                          [--network NAME]
set -euo pipefail

SYNMON_USER="${SYNMON_USER:-synmon}"
SYNMON_HOME="${SYNMON_HOME:-/var/lib/synmon}"
JOURNEYS_DIR="${SYNMON_JOURNEYS_DIR:-/etc/synmon/journeys}"
IMAGE="${SYNMON_IMAGE:-registry.internal.example/synmon/executor@sha256:REPLACE_WITH_DIGEST}"
# systemd OnCalendar expression; the default runs every 5 minutes on the clock.
SCHEDULE="${SYNMON_SCHEDULE:-*:0/5}"
WORKER_ID="${SYNMON_WORKER_ID:-$(hostname -s)}"
AGENT_USER="${SYNMON_AGENT_USER:-}"
# Target hosts the agent plugin may send piggyback data to (/etc/synmon/allowed_hosts).
ALLOWED_HOSTS="${SYNMON_ALLOWED_HOSTS:-}"
ALLOWED_HOSTS_FILE=/etc/synmon/allowed_hosts
# 1 = run Chromium with its own sandbox (see deploy/README.md, "Chromium sandbox").
CHROMIUM_SANDBOX="${SYNMON_CHROMIUM_SANDBOX:-0}"
# Pre-created Podman network to attach the executor to (default: Podman's default network).
NETWORK="${SYNMON_NETWORK:-}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

usage() {
  sed -n '2,11p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
}

while [[ "$#" -gt 0 ]]; do
  case "$1" in
    --image) IMAGE="$2"; shift 2 ;;
    --worker-id) WORKER_ID="$2"; shift 2 ;;
    --schedule) SCHEDULE="$2"; shift 2 ;;
    --journeys) JOURNEYS_DIR="$2"; shift 2 ;;
    --agent-user) AGENT_USER="$2"; shift 2 ;;
    --allowed-hosts) ALLOWED_HOSTS="$2"; shift 2 ;;
    --chromium-sandbox) CHROMIUM_SANDBOX=1; shift ;;
    --network) NETWORK="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown argument: $1" >&2; usage; exit 2 ;;
  esac
done

if [[ "${EUID}" -ne 0 ]]; then
  echo "must run as root" >&2
  exit 1
fi

# Values are substituted into unit files with sed: allow only characters that are safe there.
require() {
  local name="$1" value="$2" pattern="$3"
  if [[ ! "$value" =~ $pattern ]]; then
    echo "invalid ${name}: ${value}" >&2
    exit 2
  fi
}
require --image "$IMAGE" '^[A-Za-z0-9][A-Za-z0-9._/:@-]*$'
require --worker-id "$WORKER_ID" '^[A-Za-z0-9][A-Za-z0-9._-]*$'
require --journeys "$JOURNEYS_DIR" '^/[A-Za-z0-9._/-]+$'
require --schedule "$SCHEDULE" '^[A-Za-z0-9*:/.,~ -]+$'
if [[ -n "$AGENT_USER" ]]; then
  require --agent-user "$AGENT_USER" '^[a-z_][a-z0-9_-]*[$]?$'
fi
# Same host-name characters the contract and the agent plugin accept, comma-separated.
if [[ -n "$ALLOWED_HOSTS" ]]; then
  require --allowed-hosts "$ALLOWED_HOSTS" \
    '^[A-Za-z0-9][A-Za-z0-9._-]{0,252}(,[A-Za-z0-9][A-Za-z0-9._-]{0,252})*$'
fi
require --chromium-sandbox "$CHROMIUM_SANDBOX" '^[01]$'
if [[ -n "$NETWORK" ]]; then
  require --network "$NETWORK" '^[A-Za-z0-9][A-Za-z0-9_.-]*$'
fi
if [[ "$IMAGE" == *REPLACE_WITH_DIGEST* ]]; then
  echo "--image: set the executor image (the default is a placeholder)" >&2
  exit 2
fi
if [[ ! "$IMAGE" =~ @sha256:[0-9a-f]{64}$ ]]; then
  echo "warning: --image is not pinned by digest (@sha256:...): $IMAGE" >&2
fi

if ! systemd-analyze calendar "$SCHEDULE" >/dev/null; then
  echo "invalid --schedule (not a systemd OnCalendar expression): $SCHEDULE" >&2
  exit 2
fi

# 1. Unprivileged system user + group (no login shell).
if ! getent group "$SYNMON_USER" >/dev/null; then
  groupadd --system "$SYNMON_USER"
fi
if ! getent passwd "$SYNMON_USER" >/dev/null; then
  useradd --system --gid "$SYNMON_USER" --home-dir "$SYNMON_HOME" \
    --shell /sbin/nologin "$SYNMON_USER"
fi
uid="$(id -u "$SYNMON_USER")"
gid="$(id -g "$SYNMON_USER")"

# Optionally let an unprivileged agent user read the spool via membership in the synmon group.
if [[ -n "$AGENT_USER" ]]; then
  if ! getent passwd "$AGENT_USER" >/dev/null; then
    echo "--agent-user: no such user: $AGENT_USER" >&2
    exit 2
  fi
  usermod -aG "$SYNMON_USER" "$AGENT_USER"
fi

# 2. State directories: group-readable, setgid so new files inherit the synmon group.
install -d -o "$uid" -g "$gid" -m 2750 \
  "$SYNMON_HOME" "$SYNMON_HOME/spool" "$SYNMON_HOME/artifacts"
install -d -m 0755 /etc/synmon
# Journey modules are code the executor imports: root owns them, synmon may only read them.
# Re-running also fixes the owner of a directory created by an older install.sh.
install -d -o root -g "$gid" -m 0750 "$JOURNEYS_DIR"

# Target-host allowlist, read by the (root) agent plugin. Root-owned: the executor container,
# whose browser renders untrusted pages, cannot change which hosts it may report for.
if [[ -n "$ALLOWED_HOSTS" ]]; then
  tr ',' '\n' <<<"$ALLOWED_HOSTS" >"$ALLOWED_HOSTS_FILE.tmp"
  chmod 0644 "$ALLOWED_HOSTS_FILE.tmp"
  mv -f "$ALLOWED_HOSTS_FILE.tmp" "$ALLOWED_HOSTS_FILE"
fi

# 3. Env file (never overwrite an operator-edited one).
if [[ ! -f /etc/synmon/executor.env ]]; then
  install -m 0640 "$SCRIPT_DIR/executor.env.example" /etc/synmon/executor.env
  sed -i "s/^SYNMON_WORKER_ID=.*/SYNMON_WORKER_ID=${WORKER_ID}/" /etc/synmon/executor.env
fi

# 4. Render + install the Quadlet container unit and the timer.
if [[ "$CHROMIUM_SANDBOX" == 1 ]]; then
  sandbox=(-e "s|^@CHROMIUM_SANDBOX_CAP@$|AddCapability=SYS_CHROOT|"
    -e "s|^@CHROMIUM_SANDBOX_ENV@$|Environment=SYNMON_CHROMIUM_SANDBOX=1|")
else
  sandbox=(-e "/^@CHROMIUM_SANDBOX_CAP@$/d" -e "/^@CHROMIUM_SANDBOX_ENV@$/d")
fi
if [[ -n "$NETWORK" ]]; then
  network=(-e "s|^@NETWORK@$|Network=${NETWORK}|")
else
  network=(-e "/^@NETWORK@$/d")
fi
render() {
  sed -e "s|@IMAGE@|${IMAGE}|g" \
      -e "s|@SYNMON_UID@|${uid}|g" \
      -e "s|@SYNMON_GID@|${gid}|g" \
      -e "s|@JOURNEYS_DIR@|${JOURNEYS_DIR}|g" \
      -e "s|@SCHEDULE@|${SCHEDULE}|g" \
      "${sandbox[@]}" "${network[@]}" \
      "$1"
}
install -d -m 0755 /etc/containers/systemd
render "$SCRIPT_DIR/synmon-executor.container" >/etc/containers/systemd/synmon-executor.container
render "$SCRIPT_DIR/synmon-executor.timer" >/etc/systemd/system/synmon-executor.timer
chmod 0644 /etc/containers/systemd/synmon-executor.container \
  /etc/systemd/system/synmon-executor.timer

# 5. Generate the service from the Quadlet unit and enable the timer.
systemctl daemon-reload
systemctl enable --now synmon-executor.timer

if [[ -n "$NETWORK" ]] && ! podman network exists "$NETWORK"; then
  echo "warning: podman network '$NETWORK' does not exist; create it before the next run" >&2
fi
if ! podman image exists "$IMAGE"; then
  echo "warning: image not loaded yet; every run fails until you load it: $IMAGE" >&2
fi
if [[ ! -f "$ALLOWED_HOSTS_FILE" ]]; then
  echo "warning: no $ALLOWED_HOSTS_FILE; the worker service stays WARN until you re-run" \
    "with --allowed-hosts host1,host2,..." >&2
fi

cat <<EOF
synmon executor installed for worker '${WORKER_ID}' (schedule: ${SCHEDULE}).
Verify:
  systemctl status synmon-executor.timer
  systemctl start synmon-executor.service     # trigger one run now
  ls -l ${SYNMON_HOME}/spool ${SYNMON_HOME}/heartbeat.json
Remember to: load the executor image (podman load/pull from the mirror), drop journey modules into
${JOURNEYS_DIR} (owned by root, group ${SYNMON_USER}, mode 0640), and create podman secrets for
any journey credentials.
EOF

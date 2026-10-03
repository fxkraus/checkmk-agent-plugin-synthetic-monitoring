#!/bin/bash
# Run deploy/install.sh for real inside a RHEL 9 rebuild (AlmaLinux 9; `make test-deploy`, CI job
# "deploy"): real useradd/install/sed/systemd-analyze, real Podman Quadlet generator (dry run).
# Only systemctl is stubbed (no systemd as PID 1 in a container) and records its calls.
set -euo pipefail

SOURCE="$(cd "$(dirname "$0")/../.." && pwd)"
dnf install -y -q podman systemd shadow-utils diffutils >/dev/null

# Work on a copy: install.sh renders from its own directory.
work="$(mktemp -d)"
cp -r "${SOURCE}/deploy" "${work}/deploy"
install="${work}/deploy/install.sh"

stubs="$(mktemp -d)"
calls="${stubs}/systemctl.calls"
printf '#!/bin/sh\necho "$*" >>%s\n' "${calls}" >"${stubs}/systemctl"
chmod +x "${stubs}/systemctl"
export PATH="${stubs}:${PATH}"

IMAGE="registry.internal.example/synmon/executor@sha256:$(printf '%064d' 0)"
UNIT=/etc/containers/systemd/synmon-executor.container
failures=0

check() {
  local what="$1"
  shift
  if "$@"; then
    echo "ok   - ${what}"
  else
    echo "FAIL - ${what}"
    failures=$((failures + 1))
  fi
}
owner_mode() {
  local actual
  actual="$(stat -c '%U:%G %a' "$1")"
  [[ "${actual}" == "$2" ]]
}
rejects() { ! "${install}" "$@" >/dev/null 2>&1; }
quadlet_ok() {
  QUADLET_UNIT_DIRS=/etc/containers/systemd /usr/libexec/podman/quadlet -dryrun >"${work}/quadlet.out"
}

check "refuses the placeholder image" rejects
check "rejects an invalid allowed host" rejects --image "${IMAGE}" --allowed-hosts 'a.example.com,bad host'
check "rejects an invalid network name" rejects --image "${IMAGE}" --network 'x;y'
check "rejects an invalid schedule" rejects --image "${IMAGE}" --schedule 'every day'

useradd --system cmk-agent
# A journeys dir left by an older install.sh (owned by the runtime user).
install -d -m 0750 /etc/synmon/journeys
groupadd --system synmon && useradd --system --gid synmon --shell /sbin/nologin synmon
chown synmon:synmon /etc/synmon/journeys

"${install}" --image "${IMAGE}" --worker-id worker01 --schedule '*:0/10' \
  --allowed-hosts a.example.com,b.example.com --agent-user cmk-agent \
  --chromium-sandbox --network synmon-egress 2>"${work}/stderr"

check "state dirs are synmon:synmon 2750" \
  owner_mode /var/lib/synmon "synmon:synmon 2750"
check "spool dir is synmon:synmon 2750" owner_mode /var/lib/synmon/spool "synmon:synmon 2750"
check "journeys dir is fixed to root:synmon 750" owner_mode /etc/synmon/journeys "root:synmon 750"
check "allowlist is root:root 644" owner_mode /etc/synmon/allowed_hosts "root:root 644"
check "allowlist lists the hosts" \
  diff <(printf 'a.example.com\nb.example.com\n') /etc/synmon/allowed_hosts
check "agent user is in the synmon group" bash -c "id -nG cmk-agent | grep -qw synmon"
check "env file carries the worker id" grep -qx 'SYNMON_WORKER_ID=worker01' /etc/synmon/executor.env
check "no placeholder left in the unit" bash -c "! grep -v '^#' ${UNIT} | grep -q '@[A-Z_]*@'"
check "unit pins the image" grep -qx "Image=${IMAGE}" "${UNIT}"
synmon_uid="$(id -u synmon)"
check "unit runs as synmon" grep -qx "User=${synmon_uid}" "${UNIT}"
check "unit adds SYS_CHROOT for the sandbox" grep -qx 'AddCapability=SYS_CHROOT' "${UNIT}"
check "unit enables the sandbox" grep -qx 'Environment=SYNMON_CHROMIUM_SANDBOX=1' "${UNIT}"
check "unit joins the network" grep -qx 'Network=synmon-egress' "${UNIT}"
check "timer uses the schedule" grep -qx 'OnCalendar=\*:0/10' /etc/systemd/system/synmon-executor.timer
check "systemd reloaded and timer enabled" \
  diff <(printf 'daemon-reload\nenable --now synmon-executor.timer\n') "${calls}"
check "warns that the image is not loaded" grep -q "image not loaded yet" "${work}/stderr"
check "warns that the network does not exist" grep -q "network 'synmon-egress' does not exist" \
  "${work}/stderr"
check "Podman's Quadlet generator accepts the unit" quadlet_ok
check "generated service drops all caps and adds SYS_CHROOT" \
  grep -q -- '--cap-drop all --cap-add sys_chroot' "${work}/quadlet.out"
check "generated service joins the network" grep -q -- '--network synmon-egress' \
  "${work}/quadlet.out"

# Re-run without the options: idempotent, keeps operator files, drops the optional lines.
echo 'SYNMON_RUN_BUDGET_S=100' >>/etc/synmon/executor.env
"${install}" --image "${IMAGE}" 2>"${work}/stderr"
check "re-run keeps the edited env file" grep -qx 'SYNMON_RUN_BUDGET_S=100' /etc/synmon/executor.env
check "re-run keeps the allowlist" grep -qx 'b.example.com' /etc/synmon/allowed_hosts
check "re-run drops the sandbox lines" \
  bash -c "! grep -v '^#' ${UNIT} | grep -q 'SYS_CHROOT\|CHROMIUM_SANDBOX'"
check "re-run drops the network line" bash -c "! grep -q '^Network=' ${UNIT}"
check "re-run unit still passes Quadlet" quadlet_ok
check "re-run generated service has no extra capability" \
  bash -c "! grep -q -- '--cap-add' ${work}/quadlet.out"

# Without any allowlist the installer says so.
rm /etc/synmon/allowed_hosts
"${install}" --image "${IMAGE}" 2>"${work}/stderr"
check "warns about the missing allowlist" grep -q "no /etc/synmon/allowed_hosts" "${work}/stderr"

if ((failures)); then
  echo "${failures} check(s) failed" >&2
  exit 1
fi
echo "install.sh OK"

#!/usr/bin/env bash
# Smoke-test a built executor image the way deploy/synmon-executor.container runs it
# (unprivileged, read-only rootfs, all capabilities dropped, tmpfs /tmp): run the integration
# journeys against the mock site and check the spool + heartbeat it writes.
# Usage: scripts/test_image.sh IMAGE   (CONTAINER=podman to use podman instead of docker)
set -euo pipefail

image="${1:?usage: $0 IMAGE}"
engine="${CONTAINER:-docker}"
name="synmon-image-test-$$"
state="$(mktemp -d)"

cleanup() {
    "${engine}" rm --force "${name}-site" >/dev/null 2>&1 || true
    "${engine}" network rm "${name}" >/dev/null 2>&1 || true
    rm -rf "${state}"
}
trap cleanup EXIT

# The container user (uid 1000) is not the host user; the throwaway state dir must be writable.
chmod 0777 "${state}"

"${engine}" network create "${name}" >/dev/null
"${engine}" run --detach --name "${name}-site" --network "${name}" \
    --volume "${PWD}:/workspace:ro" --workdir /workspace \
    python:3.12-slim-bookworm python tests/integration/mocksite/mocksite.py 8080 >/dev/null

for _ in $(seq 1 30); do
    if "${engine}" exec "${name}-site" python -c \
        "import urllib.request; urllib.request.urlopen('http://localhost:8080/healthz')" \
        >/dev/null 2>&1; then
        break
    fi
    sleep 0.5
done

"${engine}" run --rm --network "${name}" \
    --read-only --tmpfs /tmp --cap-drop all --security-opt no-new-privileges \
    --user 1000:1000 \
    --env SYNMON_WORKER_ID=image-test \
    --env SYNMON_TIMEOUT_S=30 \
    --env SYNMON_RETRY_BACKOFF_S=0 \
    --env MOCKSITE_URL="http://${name}-site:8080" \
    --volume "${state}:/var/lib/synmon" \
    --volume "${PWD}/tests/integration/journeys:/journeys:ro" \
    "${image}"

"${engine}" run --rm --interactive --entrypoint python3 \
    --volume "${state}:/var/lib/synmon:ro" "${image}" - <<'EOF'
import json
from pathlib import Path

root = Path("/var/lib/synmon")
hb = json.loads((root / "heartbeat.json").read_text())
assert not hb["load_errors"], hb["load_errors"]
results = {}
for f in (root / "spool").glob("*.json"):
    obj = json.loads(f.read_text())
    results[obj["journey_name"]] = obj
states = {name: r["status"] for name, r in sorted(results.items())}
print("heartbeat:", {k: hb[k] for k in ("journeys_run", "journeys_failed", "executor_version")})
print("journeys: ", states)
expected = {"home": 0, "login": 0, "protected": 0, "flaky": 0, "slow": 2}
assert {k: states.get(k) for k in expected} == expected, states
assert results["home"].get("vitals"), "no web vitals captured (vendored script missing?)"
print("image OK")
EOF

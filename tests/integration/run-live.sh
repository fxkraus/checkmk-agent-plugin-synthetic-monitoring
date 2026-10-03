#!/bin/bash
# Run the live browser tests inside the digest-pinned Playwright image (`make integration`, CI job
# "live browser integration"). The browser comes from the image; every Python package from the
# uv.lock hashes, exported by `make integration` into .cache/integration first.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
CACHE="${REPO_DIR}/.cache/integration"
DEPS_DIR="$(mktemp -d)"

for f in requirements.txt test-requirements.txt; do
    if [[ ! -f "${CACHE}/${f}" ]]; then
        echo "missing ${CACHE}/${f}; run: make integration" >&2
        exit 2
    fi
done
pip=(python3 -m pip install --quiet --disable-pip-version-check --root-user-action=ignore
    --target "${DEPS_DIR}")
"${pip[@]}" --require-hashes \
    --requirement "${CACHE}/requirements.txt" --requirement "${CACHE}/test-requirements.txt"
"${pip[@]}" --no-deps "${CACHE}"/wheels/*.whl
export PYTHONPATH="${DEPS_DIR}" PYTHONDONTWRITEBYTECODE=1

cd "${REPO_DIR}"
python3 tests/integration/mocksite/mocksite.py 8080 &
site=$!
trap 'kill "${site}"' EXIT
for _ in $(seq 1 30); do
    if python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/healthz')" \
        2>/dev/null; then
        break
    fi
    sleep 0.5
done

SYNMON_INTEGRATION=1 MOCKSITE_URL=http://localhost:8080 \
    python3 -m pytest -p no:cacheprovider -q "$@" tests/integration

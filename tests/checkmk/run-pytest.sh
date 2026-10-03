#!/bin/bash
# Run the MKP tests with the Checkmk Python interpreter and libraries.
# Intended to run inside a Checkmk image (see `make test-checkmk` and the CI pytest matrix).
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
PYTHON="/omd/versions/default/bin/python3"
DEPS_DIR="$(mktemp -d)"

# The "test" dependency group with the uv.lock hashes. The Checkmk image has no uv, so the
# caller exports it first (`make test-checkmk` and the CI pytest job do).
REQUIREMENTS="${REPO_DIR}/.cache/checkmk-test-requirements.txt"
if [[ ! -f "${REQUIREMENTS}" ]]; then
    echo "missing ${REQUIREMENTS}; run: uv export --frozen --only-group test --no-emit-project --no-emit-workspace --output-file .cache/checkmk-test-requirements.txt" >&2
    exit 2
fi
"${PYTHON}" -m pip install --quiet --disable-pip-version-check --require-hashes \
    --target "${DEPS_DIR}" --requirement "${REQUIREMENTS}"

# Fail loudly instead of letting the test modules be skipped
"${PYTHON}" -c "import cmk.agent_based.v2, cmk.base.api.bakery.register"

# Some cmk modules write caches below OMD_ROOT at import time; there is no site here.
OMD_ROOT="$(mktemp -d)"
export OMD_ROOT OMD_SITE=synmon-test

# checkmk_mkp mirrors the site's local/lib/python3 (cmk_addons/…) and lib/python3 (cmk/…) parts.
cd "${REPO_DIR}"
SYNMON_CHECKMK=1 PYTHONDONTWRITEBYTECODE=1 \
PYTHONPATH="${DEPS_DIR}:${REPO_DIR}/checkmk_mkp:${REPO_DIR}/checkmk_mkp/lib/python3" \
    "${PYTHON}" -m pytest -p no:cacheprovider "$@" tests/checkmk tests/server

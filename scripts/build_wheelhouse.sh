#!/usr/bin/env bash
# Collect everything the air-gapped executor image build needs into ./wheelhouse:
# the two project wheels, every third-party wheel pinned by uv.lock, and a requirements.txt
# carrying the lock's sha256 hashes. Needs network access; run on the connected side
# (`make wheelhouse` runs it inside the dev container).
set -euo pipefail

# Must match the executor image: Ubuntu 24.04 (glibc 2.39) with Python 3.12. WHEEL_ARCH is
# x86_64 (RHEL workers) or aarch64. pip does not widen an explicit --platform to older manylinux
# tags, so all accepted ones are listed (playwright's x86_64 wheel is tagged manylinux1).
arch="${WHEEL_ARCH:-x86_64}"
python_version="3.12"
platforms=()
for tag in manylinux_2_28 manylinux_2_17 manylinux2014 manylinux1; do
    platforms+=(--platform "${tag}_${arch}")
done
out="wheelhouse"

rm -rf "${out}"
mkdir -p "${out}"

uv export --frozen --no-dev --no-emit-workspace --package synmon-executor \
    --output-file "${out}/requirements.txt"
uv build --package synmon-contract --wheel --out-dir "${out}"
uv build --package synmon-executor --wheel --out-dir "${out}"

python3 -m pip download --quiet --dest "${out}" \
    --only-binary=:all: "${platforms[@]}" \
    --python-version "${python_version}" --implementation cp \
    --require-hashes --requirement "${out}/requirements.txt"

ls -1 "${out}"

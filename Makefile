COMPOSE := docker compose -f .devcontainer/docker-compose.yml
RUN := $(COMPOSE) run --rm dev

CHECKMK_IMAGE ?= checkmk/check-mk-ultimate:2.5.0-latest

# Executor image (see deploy/README.md). CONTAINER=podman works too.
# VARIANT=ubi9 (default, Red Hat UBI 9) or playwright (the Playwright-supported Ubuntu image).
CONTAINER ?= docker
VARIANT ?= ubi9
EXECUTOR_IMAGE ?= synmon-executor:$(VARIANT)
PLAYWRIGHT_IMAGE ?= mcr.microsoft.com/playwright/python:v1.63.0-noble@sha256:72bd171a9ffc2b4b59532aaa6210e21014d07093120dc25528870c0b840da1f0
BASE_IMAGE ?= registry.access.redhat.com/ubi9/ubi-minimal:9.8-1790754119@sha256:1d7c5517a4a1a8e2688620b39ee980e82505ca1ab7ae5541b5463120ae9b3897
IMAGE_PLATFORM ?= linux/amd64
WHEEL_ARCH ?= x86_64
CONTAINERFILE_ubi9 := executor/Containerfile
CONTAINERFILE_playwright := executor/Containerfile.playwright
CONTAINERFILE = $(or $(CONTAINERFILE_$(VARIANT)),$(error VARIANT must be ubi9 or playwright))

.PHONY: test test-checkmk test-deploy lint typecheck secrets format schema mkp checkmk-up checkmk-down integration \
	wheelhouse image image-test hooks

test:
	$(RUN) uv run pytest -q

# The Checkmk image has no uv: export the hashed test requirements for run-pytest.sh first.
test-checkmk:
	$(RUN) uv export --frozen --only-group test --no-emit-project --no-emit-workspace --quiet \
		--output-file .cache/checkmk-test-requirements.txt
	docker run --rm --platform linux/amd64 -v "$$PWD:/source:ro" \
		--entrypoint /source/tests/checkmk/run-pytest.sh $(CHECKMK_IMAGE) -q

mkp:
	$(RUN) uv run python scripts/build_mkp.py

# Connected side: collect the wheels the offline image build installs from.
wheelhouse:
	$(COMPOSE) run --rm -e WHEEL_ARCH=$(WHEEL_ARCH) dev scripts/build_wheelhouse.sh

# Needs only ./wheelhouse and the Playwright base image, so it also runs air-gapped.
image:
	$(CONTAINER) build --platform $(IMAGE_PLATFORM) --build-arg PLAYWRIGHT_IMAGE=$(PLAYWRIGHT_IMAGE) \
		--build-arg BASE_IMAGE=$(BASE_IMAGE) -f $(CONTAINERFILE) -t $(EXECUTOR_IMAGE) .

# deploy/install.sh for real in a RHEL 9 rebuild (only systemctl stubbed; Quadlet dry run).
RHEL_TEST_IMAGE ?= docker.io/library/almalinux:9@sha256:9819dc675b67b595c2b59e42be7763fca1a8bb217fa5944e04daa22e9a64db16
test-deploy:
	docker run --rm -v "$$PWD:/source:ro" --entrypoint /source/tests/deploy/run-install-test.sh \
		$(RHEL_TEST_IMAGE)

# SECCOMP_PROFILE=<file> also runs Chromium with its own sandbox (see scripts/test_image.sh).
image-test:
	CONTAINER=$(CONTAINER) SECCOMP_PROFILE=$(SECCOMP_PROFILE) scripts/test_image.sh $(EXECUTOR_IMAGE)

# pre-commit runs the same hooks as the CI lint job (ruff, shellcheck, hadolint, actionlint,
# gitleaks, hygiene); mypy needs the workspace deps, so it runs separately.
# core.fileMode=false makes the executable-bit hooks read modes from the git index: Docker
# Desktop bind mounts on macOS report bogus execute bits (CI's native checkout does not).
lint:
	$(COMPOSE) run --rm -e GIT_CONFIG_COUNT=1 -e GIT_CONFIG_KEY_0=core.fileMode \
		-e GIT_CONFIG_VALUE_0=false dev \
		sh -c "uv run --locked pre-commit run --all-files --show-diff-on-failure && uv run --locked mypy"

typecheck:
	$(RUN) uv run --locked mypy

# Reject non-Conventional-Commit messages locally (CI checks PRs too). The hook only needs the
# host's python3 (standard library), nothing is installed.
hooks:
	printf '#!/bin/sh\nexec python3 scripts/check_commits.py --message-file "$$1"\n' \
		>"$$(git rev-parse --git-path hooks)/commit-msg"
	chmod +x "$$(git rev-parse --git-path hooks)/commit-msg"

# Full git history, like the CI secrets job.
secrets:
	docker run --rm -v "$$PWD:/repo:ro" ghcr.io/gitleaks/gitleaks:v8.30.1 git --redact --verbose /repo

format:
	$(RUN) uv run ruff format .

schema:
	$(RUN) uv run python -m synmon_contract.schema_export schema

checkmk-up:
	$(COMPOSE) up -d checkmk

checkmk-down:
	$(COMPOSE) down

# Live browser tests in the digest-pinned Playwright image (the same browser the executor image
# ships). The image has no uv: export the hashed requirements and build the project wheels first.
integration:
	$(RUN) sh -c "rm -rf .cache/integration \
		&& uv export --frozen --no-dev --no-emit-workspace --package synmon-executor --quiet \
			--output-file .cache/integration/requirements.txt \
		&& uv export --frozen --only-group test --no-emit-project --no-emit-workspace --quiet \
			--output-file .cache/integration/test-requirements.txt \
		&& uv build --quiet --package synmon-contract --wheel --out-dir .cache/integration/wheels \
		&& uv build --quiet --package synmon-executor --wheel --out-dir .cache/integration/wheels"
	docker run --rm --platform $(IMAGE_PLATFORM) -v "$$PWD:/source:ro" \
		--entrypoint /source/tests/integration/run-live.sh $(PLAYWRIGHT_IMAGE)

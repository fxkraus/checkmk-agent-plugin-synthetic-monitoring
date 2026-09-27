COMPOSE := docker compose -f .devcontainer/docker-compose.yml
RUN := $(COMPOSE) run --rm dev

CHECKMK_IMAGE ?= checkmk/check-mk-ultimate:2.5.0-latest

# Executor image (see deploy/README.md). CONTAINER=podman works too.
# VARIANT=ubi9 (default, Red Hat UBI 9) or playwright (the Playwright-supported Ubuntu image).
CONTAINER ?= docker
VARIANT ?= ubi9
EXECUTOR_IMAGE ?= synmon-executor:$(VARIANT)
PLAYWRIGHT_IMAGE ?= mcr.microsoft.com/playwright/python:v1.49.0-noble
BASE_IMAGE ?= registry.access.redhat.com/ubi9/ubi-minimal:latest
IMAGE_PLATFORM ?= linux/amd64
WHEEL_ARCH ?= x86_64
CONTAINERFILE_ubi9 := executor/Containerfile
CONTAINERFILE_playwright := executor/Containerfile.playwright
CONTAINERFILE = $(or $(CONTAINERFILE_$(VARIANT)),$(error VARIANT must be ubi9 or playwright))

.PHONY: test test-checkmk lint typecheck secrets format schema mkp checkmk-up checkmk-down integration \
	wheelhouse image image-test

test:
	$(RUN) uv run pytest -q

test-checkmk:
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

image-test:
	CONTAINER=$(CONTAINER) scripts/test_image.sh $(EXECUTOR_IMAGE)

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

integration:
	$(COMPOSE) up -d mocksite
	$(COMPOSE) run --rm playwright sh -c "pip install --quiet ./contract ./executor pytest && SYNMON_INTEGRATION=1 MOCKSITE_URL=http://mocksite:8080 pytest tests/integration -q"
	$(COMPOSE) stop mocksite

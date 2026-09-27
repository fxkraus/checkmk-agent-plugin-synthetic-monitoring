COMPOSE := docker compose -f .devcontainer/docker-compose.yml
RUN := $(COMPOSE) run --rm dev

CHECKMK_IMAGE ?= checkmk/check-mk-ultimate:2.5.0-latest

.PHONY: test test-checkmk lint typecheck secrets format schema mkp checkmk-up checkmk-down integration

test:
	$(RUN) uv run pytest -q

test-checkmk:
	docker run --rm --platform linux/amd64 -v "$$PWD:/source:ro" \
		--entrypoint /source/tests/checkmk/run-pytest.sh $(CHECKMK_IMAGE) -q

mkp:
	$(RUN) uv run python scripts/build_mkp.py

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

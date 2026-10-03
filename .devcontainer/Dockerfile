# Mirror both images to the internal registry before go-live. uv must match [tool.uv]
# required-version in pyproject.toml (tests/test_uv_pins.py).
FROM python:3.12-slim-bookworm@sha256:54c85f3c47607a77f32adec749d3c81d1348bf25833671f512b26a9b6d778cb3
COPY --from=ghcr.io/astral-sh/uv:0.9.30@sha256:538e0b39736e7feae937a65983e49d2ab75e1559d35041f9878b7b7e51de91e4 /uv /uvx /bin/
RUN apt-get update \
    && apt-get install -y --no-install-recommends git make ca-certificates \
    && rm -rf /var/lib/apt/lists/*
# The workspace is bind-mounted with the host user's uid; pre-commit runs git inside it.
RUN git config --system --add safe.directory /workspace
ENV UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PRE_COMMIT_HOME=/pre-commit-cache
WORKDIR /workspace

# Pin base + uv by tag now; pin by digest and mirror to the internal registry before go-live.
FROM python:3.12-slim-bookworm
COPY --from=ghcr.io/astral-sh/uv:0.5.11 /uv /uvx /bin/
RUN apt-get update \
    && apt-get install -y --no-install-recommends git make ca-certificates \
    && rm -rf /var/lib/apt/lists/*
# The workspace is bind-mounted with the host user's uid; pre-commit runs git inside it.
RUN git config --system --add safe.directory /workspace
ENV UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PRE_COMMIT_HOME=/pre-commit-cache
WORKDIR /workspace

# Build context: the repository root (the package depends on the workspace lock file and on
# the shared Moroccan calendar).
FROM python:3.12.16-slim-bookworm

COPY --from=ghcr.io/astral-sh/uv:0.13.9 /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Dependencies first, so that code changes do not invalidate this layer.
COPY pyproject.toml uv.lock ./
COPY services/event-generator/pyproject.toml services/event-generator/pyproject.toml
RUN uv sync --frozen --no-dev --no-install-workspace --package event-generator

COPY services/event-generator services/event-generator
COPY semantic/calendar semantic/calendar
RUN uv sync --frozen --no-dev --package event-generator \
    && useradd --system --uid 10001 generator

USER generator
ENV SENTINEL_GEN_CALENDAR=/app/semantic/calendar/morocco.yaml
EXPOSE 8094
ENTRYPOINT ["sentinel-gen"]
CMD ["--help"]

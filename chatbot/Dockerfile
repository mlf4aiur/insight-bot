FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy\
    UV_PYTHON_DOWNLOADS=0

WORKDIR /app

RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project --no-dev

COPY . /app

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev


FROM python:3.13-slim-bookworm AS runtime

ENV PATH="/app/.venv/bin:$PATH" \
    HOME="/app"

WORKDIR /app

RUN addgroup --system app && \
    adduser --system --ingroup app --home /app app && \
    chown -R app:app /app

# Copy the application from the builder
COPY --from=builder --chown=app:app /app /app

USER app

EXPOSE 8000

ENTRYPOINT ["streamlit", "run"]
CMD ["app/main.py", "--server.address=0.0.0.0", "--server.port=8000", "--server.headless=true"]

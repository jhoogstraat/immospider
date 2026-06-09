ARG UV_VERSION=0.11.19

FROM ghcr.io/astral-sh/uv:${UV_VERSION}-python3.14-trixie-slim

ENV UV_PYTHON_DOWNLOADS=0 \
    UV_NO_DEV=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONFAULTHANDLER=1 \
    PIP_NO_CACHE_DIR=1 \
    DEBIAN_FRONTEND=noninteractive

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates tini \
    && groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --home-dir /home/app --create-home --shell /usr/sbin/nologin app \
    && mkdir -p /data /ms-playwright \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock ./

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-editable --no-install-project \
    && uv run --locked --no-sync python -m patchright install --with-deps chromium \
    && rm -rf /var/lib/apt/lists/* /tmp/* \
    && chown -R app:app /home/app /data /ms-playwright

COPY src ./src

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-editable

WORKDIR /data
USER app

ENTRYPOINT ["/usr/bin/tini", "--", "uv", "run", "--project", "/app", "--locked", "--no-sync", "listing-scraper"]
CMD ["--help"]

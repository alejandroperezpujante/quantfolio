FROM python:3.14-slim-trixie

COPY --from=ghcr.io/astral-sh/uv:0.13.7 /uv /uvx /usr/local/bin/

ENV UV_PROJECT_ENVIRONMENT=/home/developer/quantfolio-venv \
    UV_CACHE_DIR=/home/developer/.cache/uv \
    UV_LINK_MODE=copy \
    RUFF_CACHE_DIR=/home/developer/.cache/ruff \
    MYPY_CACHE_DIR=/home/developer/.cache/mypy \
    PATH=/home/developer/quantfolio-venv/bin:${PATH}

RUN apt-get update \
    && apt-get install --no-install-recommends -y ca-certificates git sudo \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 1000 developer \
    && useradd --uid 1000 --gid developer --create-home --shell /bin/bash developer \
    && printf 'developer ALL=(root) NOPASSWD:ALL\n' > /etc/sudoers.d/developer \
    && chmod 0440 /etc/sudoers.d/developer

WORKDIR /workspaces/quantfolio

COPY pyproject.toml uv.lock README.md LICENSE.txt ./

RUN uv sync --frozen --no-install-project \
    && chown -R developer:developer /home/developer

USER developer

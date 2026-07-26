ARG UBUNTU_VERSION="24.04"
FROM ubuntu:${UBUNTU_VERSION} AS builder

WORKDIR /pigbot

COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

RUN apt-get update && apt-get install -y --no-install-recommends build-essential gcc git python3 && \
    rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

FROM ubuntu:${UBUNTU_VERSION} AS build-image

WORKDIR /pigbot

COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

RUN apt-get update && apt-get install -y --no-install-recommends python3 ffmpeg && \
    rm -rf /var/lib/apt/lists/*

COPY --from=builder /pigbot/.venv /pigbot/.venv
COPY ./app/ ./app/
COPY pyproject.toml uv.lock ./

ENV PATH="/pigbot/.venv/bin:$PATH"

RUN useradd --create-home appuser && \
    mkdir -p /pigbot/app/downloads && \
    chown -R appuser:appuser /pigbot
USER appuser

WORKDIR /pigbot/app
ENTRYPOINT ["python3", "main.py"]

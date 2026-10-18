# Linux shell for running verifiers v1 (Unix-only) from a Windows host. Uses the host's
# Docker through the mounted socket; the venv and caches live in the mounted repo (.tmp/).
FROM python:3.13-slim
COPY --from=docker:28-cli /usr/local/bin/docker /usr/local/bin/docker
COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /usr/local/bin/uv
ENV UV_PROJECT_ENVIRONMENT=/work/.tmp/linux-venv \
    UV_CACHE_DIR=/work/.tmp/linux-uv-cache \
    UV_LINK_MODE=copy \
    DATABASE_URL=postgresql+psycopg://gym:gym@host.docker.internal:5433/gym
WORKDIR /work

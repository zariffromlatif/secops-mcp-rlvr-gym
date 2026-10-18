#!/bin/sh
# Build the per-rollout box image used by secops-gym-patches. It is tagged with the published
# name too, so local runs use this build instead of pulling from GHCR.
set -e
cd "$(dirname "$0")/.."
uv run python scripts/sync_envs.py
TAG="${1:-ghcr.io/zariffromlatif/secops-gym-task:0.1}"
docker build -t "$TAG" -t secops-gym-task:0.1 environments/secops_gym_patches/secops_gym_patches/image

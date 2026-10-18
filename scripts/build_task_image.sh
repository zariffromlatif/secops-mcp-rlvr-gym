#!/bin/sh
# Build the per-rollout box image used by secops-gym-patches.
set -e
cd "$(dirname "$0")/.."
uv run python scripts/sync_envs.py
docker build -t "${1:-secops-gym-task:0.1}" environments/secops_gym_patches/secops_gym_patches/image

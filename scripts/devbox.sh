#!/bin/sh
# Run a command in the Linux devbox (verifiers v1 is Unix-only), e.g.:
#   sh scripts/devbox.sh uv run --no-sync vf-validate secops_gym_patches --runtime.type docker
#
# verifiers bind-mounts temp sockets into sibling containers, so TMPDIR must be a path that
# exists identically on the Docker host: /tmp/vfshare is shared between both.
set -e
cd "$(dirname "$0")/.."
docker image inspect secops-gym-devbox >/dev/null 2>&1 || docker build -q -t secops-gym-devbox runtime/devbox >/dev/null
MSYS_NO_PATHCONV=1 docker run --rm -i \
    -v /var/run/docker.sock:/var/run/docker.sock \
    -v "$(pwd -W 2>/dev/null || pwd):/work" \
    -v /tmp/vfshare:/tmp/vfshare -e TMPDIR=/tmp/vfshare \
    --add-host host.docker.internal:host-gateway \
    secops-gym-devbox "$@"

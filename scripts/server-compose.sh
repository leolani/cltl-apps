#!/usr/bin/env bash
# `docker compose` for this checkout's public server deployment: the server
# role (templates/server) plus modules/reverse-proxy. The one place the -f
# list lives, so the installer, the systemd unit, add-tenant.sh and a person
# at the shell all run the same project:
#
#   scripts/server-compose.sh ps
#   scripts/server-compose.sh logs -f caddy
#
# Any arguments are passed straight to `docker compose`. A
# config/compose.override.yml, if present, is merged in last: a local,
# gitignored escape hatch (the test harness in scripts/test/ uses it to add
# an ACME test server). Relative paths in it resolve against
# modules/event-bus/, the first file's directory, so use absolute ones.
set -euo pipefail

CLTL_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=scripts/common.sh
source "$CLTL_ROOT/scripts/common.sh"
cd "$CLTL_ROOT"

files=(
    -f modules/event-bus/docker-compose.yml
    -f modules/backend/docker-compose.yml
    -f modules/eliza/docker-compose.yml
    -f modules/vad-asr/docker-compose.yml
    -f modules/emissor/docker-compose.yml
    -f modules/reverse-proxy/docker-compose.yml
)
env_files=(--env-file config/server.env)
# A GPU server (templates/gpu-server, scripts/install-gpu-server.sh).
if [[ -f config/gpu-server.env ]]; then
    files+=(-f modules/whisper/docker-compose.yml -f modules/ollama/docker-compose.yml
            -f modules/vlm-object/docker-compose.yml)
    env_files+=(--env-file config/gpu-server.env)
fi
if [[ -f config/compose.override.yml ]]; then
    files+=(-f config/compose.override.yml)
fi

docker_cli compose "${env_files[@]}" "${files[@]}" "$@"

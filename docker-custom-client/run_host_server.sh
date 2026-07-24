#!/usr/bin/env bash
set -euo pipefail

VENV_DIR="$(dirname "$0")/venv"

if [ ! -d "$VENV_DIR" ]; then
    echo "Creating virtual environment at $VENV_DIR ..."
    python3 -m venv "$VENV_DIR"
    "$VENV_DIR/bin/pip" install --quiet --upgrade pip
    "$VENV_DIR/bin/pip" install 'cltl-backend[host]'
fi

exec "$VENV_DIR/bin/leoserv" \
    --rate 16000 \
    --channels 1 \
    --frame_duration 30 \
    --port 8000

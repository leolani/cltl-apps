#!/usr/bin/env bash
set -euo pipefail

VENV_DIR="$(dirname "$0")/venv"

# All three from the ref_scenarios branch, as custom-module/requirements.notebook.txt
# pins them, so leoserv runs the same cltl-backend, cltl.combot and emissor as
# the containers rather than PyPI's: the published cltl-backend 1.0.dev0 (and
# main) lack the /sound endpoint that [cltl.backend.text_output] remote_type:
# sound posts speech to, and emissor is listed explicitly so cltl.combot's own
# dependency on it does not resolve to PyPI's. Moving refs are installed once;
# delete venv/ to pick up newer commits. Building emissor from git only works
# cleanly on Python 3.10 (see requirements.notebook.txt).
REQUIREMENTS=(
    'emissor @ git+https://github.com/leolani/emissor.git@ref_scenarios'
    'cltl.combot @ git+https://github.com/leolani/cltl-combot.git@ref_scenarios'
    'cltl-backend[host] @ git+https://github.com/leolani/cltl-backend.git@ref_scenarios'
)

# Keyed on leoserv, not the directory, so an interrupted install is retried.
if [ ! -x "$VENV_DIR/bin/leoserv" ]; then
    echo "Creating virtual environment at $VENV_DIR ..."
    python3 -m venv "$VENV_DIR"
    "$VENV_DIR/bin/pip" install --quiet --upgrade pip
    "$VENV_DIR/bin/pip" install "${REQUIREMENTS[@]}"
fi

# These flags mirror the platform baseline in templates/common/config: --rate,
# --channels and --frame_duration are [cltl.audio] sampling_rate, channels and
# frame_size (480 samples at 16 kHz is 30 ms), and --resolution is
# [cltl.video] resolution.
#
# --resolution is not a cosmetic default. leoserv's own default is NATIVE,
# whatever the webcam happens to offer, and the containerised backend does not
# override it: with [cltl.backend] run_server False it proxies this server
# rather than opening a camera, so it asks leoserv what the resolution is
# instead of telling it. Every frame recorded at [cltl.backend.image] rate is
# then stored and persisted at that size, so NATIVE on a modern webcam fills
# storage/ for no benefit to anything downstream. VGA (640x480) is what
# [cltl.video] asks for and plenty for the Monitoring tab.
exec "$VENV_DIR/bin/leoserv" \
    --rate 16000 \
    --channels 1 \
    --frame_duration 30 \
    --resolution VGA \
    --port 8000

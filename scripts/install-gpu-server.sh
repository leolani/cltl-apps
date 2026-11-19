#!/usr/bin/env bash
# Installs and starts a public cltl-apps GPU SERVER on Ubuntu 22.04 or 24.04
# with an NVIDIA GPU: everything scripts/install-server.sh sets up, plus
# speech recognition on the GPU (modules/whisper, whisper.cpp), a local LLM
# server (modules/ollama) and object recognition with it (modules/vlm-object),
# configured from templates/gpu-server. See
# doc/DEPLOYMENT.md#a-gpu-server.
#
# Run it as your normal login user, not with sudo, exactly like
# install-server.sh — every option of that script is accepted here and passed
# on to it. On a fresh machine, with the attached volume at ~/data/<volume>:
#
#   curl -fsSL https://raw.githubusercontent.com/leolani/cltl-apps/main/scripts/install-gpu-server.sh \
#       | bash -s -- --dir ~/data/<volume>/cltl-apps \
#                    --hostname combot.example.org --email you@example.org
#
# or, from a checkout:
#
#   scripts/install-gpu-server.sh --hostname combot.example.org --email you@example.org
#
# Needs the NVIDIA driver already installed and loaded, 580 or newer (the
# whisper.cpp image is a CUDA 13 build). It is not installed here, because that
# takes a reboot; GPU cloud images usually ship it. Otherwise:
#
#   sudo ubuntu-drivers install --gpgpu && sudo reboot
#
# What this script adds to install-server.sh, in order:
#   1. the NVIDIA Container Toolkit, pinned, from NVIDIA's apt repository;
#   2. the Whisper model file in storage/whisper/, checked against its sha256;
#   3. install-server.sh itself, with config/custom.config from
#      templates/gpu-server (on a first run only — an existing one is kept);
#   4. a `docker run --gpus all` smoke test, and only then
#      config/gpu-server.env, whose presence makes scripts/server-compose.sh
#      start modules/whisper, modules/ollama and modules/vlm-object with the
#      rest;
#   5. the Ollama model, pulled into storage/ollama/;
#   6. checks: a transcription, a generation on the GPU, and /ollama/ on 443
#      refusing requests without its bearer token (in config/credentials).
#
# Options of its own (everything else goes to install-server.sh, see its --help):
#   --ollama-model TAG  the model to pull and name in config/custom.config, for
#                       [cltl.llm.ollama] and modules/vlm-object alike (default:
#                       qwen3-vl:8b-instruct-q4_K_M; keep it a vision model).
#                       Remembered; a model pulled earlier is not removed.
#
# Run it again at any time: it upgrades like install-server.sh, and every step
# above is skipped when already done. Downloads happen here, never at boot.
set -euo pipefail

DEFAULT_REPO=https://github.com/leolani/cltl-apps.git
NVIDIA_TOOLKIT_VERSION=1.20.2-1
MIN_DRIVER=580
DEFAULT_OLLAMA_MODEL=qwen3-vl:8b-instruct-q4_K_M
WHISPER_MODEL=ggml-large-v3-turbo.bin
WHISPER_MODEL_SHA256=1fc70f774d38eb169993ac391eea357ef47c88757ef72ee5943879b7e8e2bc69
WHISPER_MODEL_URL=https://huggingface.co/ggerganov/whisper.cpp/resolve/main/$WHISPER_MODEL

ollama_model_arg="" version_arg="" dir="" repo=$DEFAULT_REPO ref=main pull=1 test_ca_file=""
server_args=()
original_args=("$@")
start_dir=$PWD

usage() { sed -n '2,/^set -euo/p' "${BASH_SOURCE[0]}" 2> /dev/null | sed '$d; s/^# \{0,1\}//'; }

# Our own options are consumed; the rest is install-server.sh's, and the few
# of those this script needs as well are read on the way past.
while [[ $# -gt 0 ]]; do
    case $1 in
        --ollama-model) ollama_model_arg=${2:?}; shift ;;
        --no-pull) pull=0 ;;
        --dir) dir=${2:?}; server_args+=("$1" "$2"); shift ;;
        --repo) repo=${2:?}; server_args+=("$1" "$2"); shift ;;
        --ref) ref=${2:?}; server_args+=("$1" "$2"); shift ;;
        --version) version_arg=${2:?}; server_args+=("$1" "$2"); shift ;;
        # Files named relative to where we were run; install-server.sh runs
        # from inside the checkout.
        --test-ca-file) test_ca_file=$(realpath "${2:?}"); server_args+=("$1" "$test_ca_file"); shift ;;
        --tenants) server_args+=("$1" "$(realpath "${2:?}")"); shift ;;
        -h|--help) usage; exit 0 ;;
        *) server_args+=("$1") ;;
    esac
    shift
done

if [[ -n $ollama_model_arg && ! $ollama_model_arg =~ ^[A-Za-z0-9._:/-]+$ ]]; then
    echo "invalid --ollama-model '$ollama_model_arg'" >&2
    exit 2
fi
[[ $EUID -ne 0 ]] || [[ " ${server_args[*]} " == *" --allow-root "* ]] \
    || { echo "run this as your normal login user, not as root (see --help)" >&2; exit 1; }

# --- 1. Bootstrap: find or make the checkout, then run from inside it ----------
# The same as install-server.sh, so that what runs always matches the modules
# it installs.

self=${BASH_SOURCE[0]:-}
self_root=""
if [[ -n $self && -f $self ]]; then
    self_root=$(cd "$(dirname "$self")/.." && pwd)
    [[ -f $self_root/modules/whisper/docker-compose.yml ]] || self_root=""
fi

if [[ -z $self_root ]]; then
    command -v git > /dev/null || { sudo apt-get update -q && sudo apt-get install -y -q git; }
    [[ -n $dir ]] || { echo "--dir is required when the script is not run from a checkout (see --help)" >&2; exit 2; }
    dir=$(realpath -m "$dir")
    if [[ -d $dir/.git ]]; then
        echo "==> Updating $dir to $ref" >&2
        git -c safe.directory="$dir" -C "$dir" fetch -q origin "$ref"
        git -c safe.directory="$dir" -C "$dir" checkout -q "$ref"
        git -c safe.directory="$dir" -C "$dir" merge -q --ff-only "origin/$ref" 2> /dev/null || true
    else
        [[ ! -e $dir ]] || { echo "$dir exists and is not a checkout" >&2; exit 1; }
        mkdir -p "$(dirname "$dir")"
        echo "==> Cloning $repo ($ref) into $dir" >&2
        git clone -q --branch "$ref" "$repo" "$dir"
    fi
    exec "$dir/scripts/install-gpu-server.sh" "${original_args[@]}" --no-pull
fi

CLTL_ROOT=$self_root
cd "$CLTL_ROOT"
# shellcheck source=scripts/common.sh
source "$CLTL_ROOT/scripts/common.sh"
require_owner
command -v sudo > /dev/null || [[ $EUID -eq 0 ]] || die "sudo is required"

if ((pull)) && [[ -z $(git -c safe.directory="$CLTL_ROOT" status --porcelain --untracked-files=no) ]] \
        && git -c safe.directory="$CLTL_ROOT" symbolic-ref -q HEAD > /dev/null; then
    log "Updating the checkout"
    if git -c safe.directory="$CLTL_ROOT" pull -q --ff-only; then
        cd "$start_dir"
        exec "$CLTL_ROOT/scripts/install-gpu-server.sh" "${original_args[@]}" --no-pull
    fi
    warn "git pull failed; continuing with the checkout as it is"
fi

# --- 2. Preflight: the GPU ----------------------------------------------------------

[[ $(uname -m) == x86_64 ]] || die "the whisper.cpp CUDA image is built for x86_64 only, not $(uname -m)"
nvidia-smi > /dev/null 2>&1 \
    || die "no working NVIDIA driver (nvidia-smi fails). Install one and reboot, then run this again:" \
           "sudo ubuntu-drivers install --gpgpu && sudo reboot"
driver=$(nvidia-smi --query-gpu=driver_version --format=csv,noheader | head -n 1)
((${driver%%.*} >= MIN_DRIVER)) \
    || die "NVIDIA driver $driver is too old for the CUDA 13 images; $MIN_DRIVER or newer is needed" \
           "(sudo ubuntu-drivers install --gpgpu && sudo reboot)"
vram_mb=$(nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits | sort -n | tail -n 1)
log "GPU: $(nvidia-smi --query-gpu=name --format=csv,noheader | head -n 1), ${vram_mb} MiB, driver $driver"
((vram_mb >= 16000)) || warn "${vram_mb} MiB of VRAM; Whisper large-v3-turbo plus the default model need about 12 GB"
mkdir -p storage/whisper storage/ollama
free_gb=$(df -P --block-size=1G storage | awk 'NR == 2 { print $4 }')
((free_gb >= 60)) || warn "${free_gb} GB free disk; the images, Whisper and Ollama models need about 60 GB"

ollama_model=${ollama_model_arg:-$(kv_get "$CLTL_STATE_FILE" OLLAMA_MODEL)}
ollama_model=${ollama_model:-$DEFAULT_OLLAMA_MODEL}

# --- 3. NVIDIA Container Toolkit -------------------------------------------------------
# Docker's `--gpus` (and Compose's `driver: nvidia` device reservation) calls the
# toolkit's hook directly, so no runtime entry in /etc/docker/daemon.json is
# needed — which leaves that file to install-server.sh, which writes Docker's
# data-root there.

installed=$(dpkg-query -W -f='${Version}' nvidia-container-toolkit 2> /dev/null || true)
if [[ $installed != "$NVIDIA_TOOLKIT_VERSION" ]]; then
    log "Installing the NVIDIA Container Toolkit $NVIDIA_TOOLKIT_VERSION"
    as_root env DEBIAN_FRONTEND=noninteractive apt-get update -q
    as_root env DEBIAN_FRONTEND=noninteractive apt-get install -y -q --no-install-recommends \
        ca-certificates curl gnupg > /dev/null
    curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey \
        | gpg --batch --dearmor | as_root tee /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg > /dev/null
    curl -fsSL https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list \
        | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' \
        | as_root tee /etc/apt/sources.list.d/nvidia-container-toolkit.list > /dev/null
    as_root env DEBIAN_FRONTEND=noninteractive apt-get update -q
    as_root env DEBIAN_FRONTEND=noninteractive apt-get install -y -q --allow-downgrades \
        "nvidia-container-toolkit=$NVIDIA_TOOLKIT_VERSION" \
        "nvidia-container-toolkit-base=$NVIDIA_TOOLKIT_VERSION" \
        "libnvidia-container-tools=$NVIDIA_TOOLKIT_VERSION" \
        "libnvidia-container1=$NVIDIA_TOOLKIT_VERSION"
fi

# --- 4. The Whisper model ---------------------------------------------------------------

model_file=storage/whisper/$WHISPER_MODEL
if [[ -f $model_file ]] && sha256sum "$model_file" | grep -q "^$WHISPER_MODEL_SHA256 "; then
    :
else
    log "Downloading the Whisper model $WHISPER_MODEL (1.6 GB)"
    curl -fL --retry 3 -C - -o "$model_file.part" "$WHISPER_MODEL_URL"
    sha256sum "$model_file.part" | grep -q "^$WHISPER_MODEL_SHA256 " \
        || { rm -f "$model_file.part"; die "$WHISPER_MODEL does not match its sha256; removed, run again"; }
    mv "$model_file.part" "$model_file"
fi

# --- 5. The server ------------------------------------------------------------------------
# config/custom.config from the GPU template, before install-server.sh would
# copy the plain server's; it then adds the event bus password to it as usual.
# config/gpu-server.env is held back on a first run until the GPU is proven
# to work in a container (step 6), so a broken toolkit cannot take the rest
# of the server down with it.

mkdir -p config
[[ -f config/default.config ]] || cp templates/common/config/* config/
[[ -f config/custom.config ]] || cp templates/gpu-server/config/custom.config config/
# A custom.config from before modules/vlm-object has no section for it, and
# the baseline's host is a llama-server on the host, not modules/ollama.
grep -q '^\[cltl.vlm_object_recognition\]' config/custom.config \
    || ini_set config/custom.config cltl.vlm_object_recognition host http://ollama:11434
ini_set config/custom.config cltl.llm.ollama model "$ollama_model"
# Ollama refuses a model it has not pulled, so the two must agree.
ini_set config/custom.config cltl.vlm_object_recognition model "$ollama_model"
kv_set "$CLTL_STATE_FILE" OLLAMA_MODEL "$ollama_model"

# The ASR module must know [cltl.asr] implementation whisper_cpp, or it exits
# at start and takes `up --wait` — and so install-server.sh — down with it.
version=${version_arg:-$(kv_get "$CLTL_ENV_FILE" VERSION)}
asr_image=ghcr.io/leolani/cltl-asr:${version:-latest}
asr_hint="$asr_image predates [cltl.asr] implementation whisper_cpp; rebuild and publish cltl-asr, then run this again"
asr_supports_whisper_cpp() {
    docker_cli pull -q "$asr_image" > /dev/null &&
    docker_cli run --rm --entrypoint python "$asr_image" -c \
        'import inspect, cltl_service.asr.container as c; exit("whisper_cpp" not in inspect.getsource(c))'
}
vlm_image=ghcr.io/leolani/cltl-vlm-object:${version:-latest}
if command -v docker > /dev/null; then
    asr_supports_whisper_cpp || die "$asr_hint"
    # Without it, `up --wait` fails for the whole server once
    # config/gpu-server.env exists.
    docker_cli pull -q "$vlm_image" > /dev/null \
        || die "cannot pull $vlm_image; build and publish cltl-vlm-object, then run this again"
fi

log "Running install-server.sh"
"$CLTL_ROOT/scripts/install-server.sh" "${server_args[@]}" --no-pull \
    || die "install-server.sh failed. If eliza-asr exited (scripts/server-compose.sh logs eliza-asr):" \
           "$asr_hint"

# --- 6. The GPU in a container, then the GPU modules ----------------------------------------

gpu_env=()
[[ ! -f config/gpu-server.env ]] || gpu_env=(--env-file config/gpu-server.env)
whisper_image=$(docker_cli compose "${gpu_env[@]}" -f modules/whisper/docker-compose.yml config --images)
log "Checking that containers see the GPU"
docker_cli pull -q "$whisper_image" > /dev/null
docker_cli run --rm --gpus all --entrypoint nvidia-smi "$whisper_image" -L \
    || die "a container cannot use the GPU. Check the NVIDIA Container Toolkit:" \
           "docker run --rm --gpus all $whisper_image nvidia-smi"

if [[ ! -f config/gpu-server.env ]]; then
    cp templates/gpu-server/config/gpu-server.env config/
    chmod 600 config/gpu-server.env
fi
# The bearer token modules/reverse-proxy requires on /ollama/, so that an
# OpenAI client's api_key is the credential. Generated once, kept like the
# other secrets in config/credentials, and handed to caddy through this file.
ollama_token=$(kv_get "$CLTL_CREDENTIALS_FILE" OLLAMA_TOKEN)
[[ -n $ollama_token ]] || ollama_token=$(generate_secret)
kv_set "$CLTL_CREDENTIALS_FILE" OLLAMA_TOKEN "$ollama_token"
kv_set config/gpu-server.env CLTL_OLLAMA_TOKEN "$ollama_token"
log "Starting the GPU modules"
compose pull -q whisper ollama vlm-object
as_root systemctl restart cltl-server.service

# --- 7. The Ollama model --------------------------------------------------------------------

log "Pulling $ollama_model into storage/ollama (first run: several GB)"
compose exec -T ollama ollama pull "$ollama_model" < /dev/null > /dev/null

# --- 8. Checks ------------------------------------------------------------------------------

failures=0
fail() { warn "$*"; failures=$((failures + 1)); }

transcript=$(compose exec -T whisper bash -c \
    'ffmpeg -loglevel error -y -f lavfi -i anullsrc=r=16000:cl=mono -t 1 /tmp/check.wav &&
     curl -fsS -F file=@/tmp/check.wav -F response_format=json http://localhost:8080/inference' < /dev/null || true)
[[ $transcript == *'"text"'* ]] || fail "whisper did not transcribe a test file: ${transcript:-no answer}"
# Each output is captured before it is searched, never piped into `grep -q`:
# grep exits at its first match, the writer then dies of SIGPIPE, and
# pipefail turns that into a failed check although the text was there.
whisper_log=$(compose logs whisper 2>&1 || true)
grep -qiE 'CUDA|cuBLAS' <<< "$whisper_log" || fail "whisper's log shows no CUDA device; is it on the CPU?"

compose exec -T ollama ollama run "$ollama_model" "Answer with one word: OK" < /dev/null > /dev/null \
    || fail "ollama could not generate with $ollama_model"
ollama_ps=$(compose exec -T ollama ollama ps < /dev/null || true)
grep -q 'GPU' <<< "$ollama_ps" || fail "ollama ps shows $ollama_model not on the GPU"
ollama_show=$(compose exec -T ollama ollama show "$ollama_model" < /dev/null || true)
grep -qw vision <<< "$ollama_show" || warn "$ollama_model is not a vision model; images will be refused"
[[ $(compose ps --format '{{.Health}}' vlm-object) == healthy ]] \
    || fail "vlm-object is not healthy (scripts/server-compose.sh logs vlm-object)"

hostname=$(kv_get "$CLTL_ENV_FILE" CLTL_HOSTNAME)
curl_ca=()
[[ -z $test_ca_file ]] || curl_ca=(--cacert "$test_ca_file")
ollama_status() {
    curl -s -o /dev/null -w '%{http_code}' "${curl_ca[@]}" "$@" \
         --resolve "$hostname:443:127.0.0.1" "https://$hostname/ollama/v1/models" || true
}
status=$(ollama_status)
[[ $status == 401 ]] || fail "https://$hostname/ollama/ without a token: HTTP $status, expected 401"
status=$(ollama_status -H "Authorization: Bearer $ollama_token")
[[ $status == 200 ]] || fail "https://$hostname/ollama/v1/models with the token: HTTP $status, expected 200"

# --- 9. Summary -----------------------------------------------------------------------------

cat << EOF

GPU modules on https://$hostname (in addition to the server above)

  Speech recognition  whisper.cpp, $WHISPER_MODEL, internal only (http://whisper:8080)
  LLM                 https://$hostname/ollama/   model $ollama_model
                      bearer token $ollama_token
                      OpenAI clients: base_url https://$hostname/ollama/v1, api_key the token
                      e.g. curl -H "Authorization: Bearer <token>" https://$hostname/ollama/api/chat \\
                               -d '{"model": "$ollama_model", "messages": [{"role": "user", "content": "Hi"}]}'
  Object recognition  modules/vlm-object with $ollama_model: images on cltl.topic.image,
                      results on cltl.topic.object_recognition

  Models              $CLTL_ROOT/storage/whisper, $CLTL_ROOT/storage/ollama
  On this host        127.0.0.1:8090 (whisper), 127.0.0.1:11434 (ollama)

Of the platform's own modules only vlm-object calls the LLM; see doc/DEPLOYMENT.md#a-gpu-server.
EOF

if ((failures)); then
    die "$failures GPU check(s) failed; see the warnings above"
fi

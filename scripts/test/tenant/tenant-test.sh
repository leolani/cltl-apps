#!/usr/bin/env bash
# Tests a server installed by scripts/install-server.sh or
# scripts/install-gpu-server.sh from the outside, the way a tenant uses it:
# brings up a throwaway tenant here (modules/backend, context, chat-ui), runs
# the checks against the server, and tears the tenant down again. Needs only
# Docker; the checks run in containers on the tenant's own network.
#
#   scripts/test/tenant/tenant-test.sh --credentials credentials --tenants tenants.urls
#
# The two files are copies of the server's config/credentials (for the Basic
# Auth user of its storage) and config/tenants.urls (for the tenant's amqps://
# URL). The tenant must already exist on the server, e.g. from
# `scripts/add-tenant.sh test` there; use a tenant kept for testing, since the
# run leaves a conversation, its recordings and an image in the server's
# storage and EMISSOR data. With more than one tenant in the file, --tenant
# picks one. A server installed without a tenant list has a single shared
# user `tenant`, which may use any tenant id: the run then uses --tenant, or
# `test`, as its id.
#
# Checks, all by default:
#   chat     answers the consent question and sends two lines through the
#            chat UI; each must get a reply on cltl.topic.text_out or
#            cltl.topic.eliza_out (where ELIZA answers on a server that
#            frees text_out for a tenant's own module)
#   objects  uploads an image through the chat UI; an event must arrive on
#            cltl.topic.object_recognition with at least one labelled box.
#            Needs the GPU server's vlm-object, so it fails on a plain server
#   asr      a fake microphone (fake_leoserv.py, standing in for the host's
#            leoserv) plays a WAV; an AsrTextSignalEvent with text must
#            arrive on cltl.topic.text_in
#
# Options:
#   --credentials FILE  copy of the server's config/credentials (required)
#   --tenants FILE      copy of the server's config/tenants.urls (required)
#   --tenant ID         the tenant to use; required when the file lists
#                       several. With the shared user, any id (default: test)
#   --only LIST         comma-separated subset of chat,objects,asr
#   --image FILE        image for the objects check (default: image-1.jpeg here)
#   --wav FILE          16 kHz mono 16-bit speech for the asr check (default:
#                       jfk.wav here, from JFK's inaugural address)
#   --timeout SECONDS   wait per step for a result (default: 120; the first
#                       vision request after a server restart loads the
#                       model and can take a minute)
#   --keep              leave the tenant running afterwards, for a look in the
#                       chat UI; prints how to take it down
#   -v, --verbose       print every event of the tenant on the bus as JSON
#
# VERSION=<tag> pins the tenant's images, as everywhere else. Exits non-zero
# when a check fails, after printing the warnings and errors in the
# tenant containers' logs.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../../.." && pwd)"
PROJECT=cltl-tenant-test
BACKEND_IMAGE=ghcr.io/leolani/cltl-backend:${VERSION:-latest}

die() { printf '\033[1;31mERROR:\033[0m %s\n' "$*" >&2; exit 2; }
log() { printf '\033[1;34m==>\033[0m %s\n' "$*" >&2; }
usage() { sed -n '/^# Options:/,/^# VERSION/p' "$0" | sed 's/^# \{0,1\}//' >&2; exit 2; }

credentials='' tenants='' tenant='' checks=chat,objects,asr
image=$HERE/image-1.jpeg wav=$HERE/jfk.wav timeout=120 keep=0 verbose=0
while (($#)); do
    case $1 in
        --credentials) credentials=${2:?}; shift 2 ;;
        --tenants) tenants=${2:?}; shift 2 ;;
        --tenant) tenant=${2:?}; shift 2 ;;
        --only) checks=${2:?}; shift 2 ;;
        --image) image=${2:?}; shift 2 ;;
        --wav) wav=${2:?}; shift 2 ;;
        --timeout) timeout=${2:?}; shift 2 ;;
        --keep) keep=1; shift ;;
        -v | --verbose) verbose=1; shift ;;
        -h | --help) usage ;;
        *) printf 'unknown option: %s\n\n' "$1" >&2; usage ;;
    esac
done

[[ -n $credentials && -n $tenants ]] || usage
for f in "$credentials" "$tenants" "$image" "$wav"; do
    [[ -f $f ]] || die "no such file: $f"
done
IFS=, read -ra wanted <<< "$checks"
for c in "${wanted[@]}"; do
    [[ $c =~ ^(chat|objects|asr)$ ]] || die "unknown check '$c' in --only; choose from chat,objects,asr"
done
[[ $timeout =~ ^[0-9]+$ ]] || die "--timeout takes whole seconds"
image=$(cd "$(dirname "$image")" && pwd)/$(basename "$image")
wav=$(cd "$(dirname "$wav")" && pwd)/$(basename "$wav")

# config/credentials: KEY=value lines, the last active one counting.
cred() { grep -E "^$1=" "$credentials" | tail -n 1 | cut -d= -f2- || true; }
auth_user=$(cred BASIC_AUTH_USER)
auth_password=$(cred BASIC_AUTH_PASSWORD)
[[ -n $auth_user && -n $auth_password ]] ||
    die "$credentials has no BASIC_AUTH_USER/BASIC_AUTH_PASSWORD; is it the server's config/credentials?"

# config/tenants.urls: one `<id> amqps://<id>:<password>@<host>:5671/` line per tenant.
lines=()
while IFS= read -r line; do lines+=("$line"); done < <(grep -E '^[^#[:space:]]+[[:space:]]+amqps?://' "$tenants" || true)
((${#lines[@]})) || die "$tenants lists no tenant; is it the server's config/tenants.urls?"
SHARED_USER=tenant  # CLTL_SHARED_TENANT_USER in scripts/common.sh
if [[ -z $tenant ]]; then
    ((${#lines[@]} == 1)) ||
        die "$tenants lists several tenants ($(printf '%s ' "${lines[@]%% *}")); pick one with --tenant"
    tenant=${lines[0]%% *}
    [[ $tenant == "$SHARED_USER" ]] && tenant=test
fi
tenant_url='' shared_url=''
for line in "${lines[@]}"; do
    read -r id url <<< "$line"
    [[ $id == "$tenant" ]] && tenant_url=$url
    [[ $id == "$SHARED_USER" ]] && shared_url=$url
done
tenant_url=${tenant_url:-$shared_url}
[[ -n $tenant_url ]] || die "tenant '$tenant' is not in $tenants"
[[ $tenant =~ ^[a-z0-9][a-z0-9_-]*$ ]] || die "'$tenant' is not a valid tenant id"
host=$(sed -E 's#^amqps?://[^@]*@([^:/]+).*#\1#' <<< "$tenant_url")
[[ -n $host && $host != "$tenant_url" ]] || die "cannot read the server's hostname from the URL of '$tenant'"
storage="https://$auth_user:$auth_password@$host/storage"

port_free() { ! (exec 3<> "/dev/tcp/127.0.0.1/$1") 2> /dev/null; }
free_port() {  # first free port from $1 on
    local p=$1
    until port_free "$p"; do p=$((p + 1)); done
    echo "$p"
}

work=$(mktemp -d "${TMPDIR:-/tmp}/cltl-tenant-test.XXXXXX")
compose() {
    docker compose --env-file "$work/config/tenant.env" \
        -f "$work/modules/backend/docker-compose.yml" \
        -f "$work/modules/context/docker-compose.yml" \
        -f "$work/modules/chat-ui/docker-compose.yml" \
        -f "$work/mic.yml" "$@"
}
cleanup() {
    status=$?
    trap - EXIT INT TERM
    if ((keep)); then
        printf '\nThe tenant is still running; its config in %s holds the credentials. Take it down with\n' "$work"
        printf '  docker compose -p %s down && docker run --rm -v %s:/w --entrypoint rm %s -rf /w/storage && rm -rf %s\n' \
            "$PROJECT" "$work" "$BACKEND_IMAGE" "$work"
        exit "$status"
    fi
    log "tearing the tenant down"
    compose down --remove-orphans > /dev/null 2>&1 || true
    # storage/ is written by the containers as root
    docker run --rm -v "$work:/w" --entrypoint rm "$BACKEND_IMAGE" -rf /w/storage > /dev/null 2>&1 || true
    rm -rf "$work"
    exit "$status"
}
trap cleanup EXIT
trap 'exit 130' INT TERM

log "tenant '$tenant' on $host"
docker compose -p "$PROJECT" down --remove-orphans > /dev/null 2>&1 || true  # a --keep left over

# A copy of the three modules, so that their ../../config and ../../storage
# are this run's, never the checkout's.
mkdir -p "$work/modules" "$work/config" "$work/storage"
cp -R "$ROOT/modules/backend" "$ROOT/modules/context" "$ROOT/modules/chat-ui" "$work/modules/"
cp "$ROOT"/templates/common/config/* "$work/config/"
chatui_port=$(free_port 18003)
backend_port=$(free_port 19001)
cat > "$work/config/tenant.env" << EOF
CLTL_PROJECT=$PROJECT
CLTL_BACKEND_PORT=$backend_port
CLTL_CHATUI_PORT=$chatui_port
CLTL_CONTEXT_START_DELAY=0
EOF
# templates/tenant/config/custom.config, filled in for a remote server, with
# the host's microphone server replaced by the fake one (the `mic` service).
cat > "$work/config/custom.config" << EOF
[cltl.event.kombu]
tenant: $tenant
server: $tenant_url

[cltl.backend]
storage_url: $storage/
audio_storage: remote
image_storage: remote
server_audio_url: http://mic:8000
server_image_url: http://mic:8000

[cltl.backend.remote_storage]
storage_url: $storage

[cltl.backend.text_output]
remote_url: http://mic:8000

# No camera; the objects check uploads through the chat UI instead.
[cltl.backend.image]
topic:
rate: 0

[cltl.chat-ui]
monitoring_url:
EOF
chmod 600 "$work/config/custom.config"
cat > "$work/mic.yml" << EOF
services:
  mic:
    image: $BACKEND_IMAGE
    entrypoint: ["python", "-u", "/test/fake_leoserv.py", "/input/speech.wav"]
    volumes:
      - $HERE:/test:ro
      - $wav:/input/speech.wav:ro
    # The image's own healthcheck asks for the backend's /health.
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/listeners')"]
      interval: 5s
    networks:
      - cltl-platform
EOF

show_logs() {  # warnings and errors of the tenant's modules, and all of the fake mic's
    log "warnings and errors in the tenant's logs"
    compose logs --no-color backend context chatui 2> /dev/null |
        grep -E ' (WARNING|ERROR|CRITICAL) |Traceback|Error:' | tail -n 40 || true
    log "the fake microphone's log"
    compose logs --no-color mic 2> /dev/null | tail -n 20 || true
}

log "starting backend, context, chat-ui and the fake microphone"
compose up -d --wait --pull always --quiet-pull || { show_logs; die "the tenant did not come up"; }

log "running ${checks//,/, }"
status=0
export TENANT_URL=$tenant_url  # by name below, so the password stays out of ps
docker run --rm --network "$PROJECT" \
    -e TENANT_URL -e TENANT_ID="$tenant" -e CHECKS="$checks" \
    -e IMAGE=/input/image -e WAV=/input/speech.wav \
    -e IMAGE_NAME="$(basename "$image")" -e WAV_NAME="$(basename "$wav")" -e TIMEOUT="$timeout" -e VERBOSE="$verbose" \
    -v "$HERE:/test:ro" -v "$image:/input/image:ro" -v "$wav:/input/speech.wav:ro" \
    --entrypoint python "$BACKEND_IMAGE" -u /test/tenant_test.py || status=$?

((status)) && show_logs
((keep)) && printf '\nChat UI: http://localhost:%s/chatui/static/chat.html\n' "$chatui_port"
exit "$status"

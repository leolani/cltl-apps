#!/usr/bin/env bash
# Hands caddy's certificate for CLTL_HOSTNAME to RabbitMQ's AMQPS listener.
#
# caddy obtains and renews the certificate (modules/reverse-proxy) and keeps
# it in its data volume, readable by root only; RabbitMQ runs as uid 999 and
# reads storage/rabbitmq-tls/ (see modules/reverse-proxy/rabbitmq.conf). This
# copies the three files across and, when they changed, clears Erlang's PEM
# cache so that new connections get the new certificate. Open connections
# keep the one they negotiated; nothing restarts.
#
#   sync-rabbitmq-cert.sh            copy caddy's certificate if it changed
#   sync-rabbitmq-cert.sh --wait N   poll up to N seconds for caddy to have one
#   sync-rabbitmq-cert.sh --seed     only make sure some certificate exists
#
# --seed writes a self-signed certificate when the directory is empty:
# RabbitMQ will not start without one, and caddy can only obtain the real one
# once the stack is up. scripts/install-server.sh runs --seed, then --wait,
# and installs a daily systemd timer for the plain form; caddy renews about
# 30 days before expiry, so a day's lag is harmless.
set -euo pipefail

CLTL_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=scripts/common.sh
source "$CLTL_ROOT/scripts/common.sh"

RABBITMQ_UID=999

mode=sync
wait_seconds=0
while [[ $# -gt 0 ]]; do
    case $1 in
        --seed) mode=seed ;;
        --wait) wait_seconds=${2:?--wait needs a number of seconds}; shift ;;
        -h|--help) sed -n '2,21p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) die "unknown argument $1" ;;
    esac
    shift
done

require_root
hostname=$(kv_get "$CLTL_ENV_FILE" CLTL_HOSTNAME)
[[ -n $hostname ]] || die "CLTL_HOSTNAME is not set in $CLTL_ENV_FILE"

install_files() {  # leaf chain key, as files
    local leaf=$1 chain=$2 key=$3
    mkdir -p "$CLTL_TLS_DIR"
    # Each file replaced by rename, so RabbitMQ never reads a half-written one.
    install -o "$RABBITMQ_UID" -g "$RABBITMQ_UID" -m 0644 "$leaf" "$CLTL_TLS_DIR/.cert.pem"
    install -o "$RABBITMQ_UID" -g "$RABBITMQ_UID" -m 0644 "$chain" "$CLTL_TLS_DIR/.chain.pem"
    install -o "$RABBITMQ_UID" -g "$RABBITMQ_UID" -m 0600 "$key" "$CLTL_TLS_DIR/.key.pem"
    mv -f "$CLTL_TLS_DIR/.key.pem" "$CLTL_TLS_DIR/key.pem"
    mv -f "$CLTL_TLS_DIR/.cert.pem" "$CLTL_TLS_DIR/cert.pem"
    mv -f "$CLTL_TLS_DIR/.chain.pem" "$CLTL_TLS_DIR/chain.pem"
}

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

if [[ $mode == seed ]]; then
    if [[ -s $CLTL_TLS_DIR/cert.pem && -s $CLTL_TLS_DIR/chain.pem && -s $CLTL_TLS_DIR/key.pem ]]; then
        exit 0
    fi
    log "Seeding a self-signed certificate for $hostname in storage/rabbitmq-tls/"
    openssl req -x509 -newkey rsa:2048 -nodes -days 30 -subj "/CN=$hostname" \
        -addext "subjectAltName=DNS:$hostname" \
        -keyout "$work/key.pem" -out "$work/cert.pem" 2> /dev/null
    install_files "$work/cert.pem" "$work/cert.pem" "$work/key.pem"
    exit 0
fi

# caddy keeps one directory per ACME issuer; after a switch (staging to
# production, say) the newest certificate is the one it serves.
find_caddy_cert() {
    # shellcheck disable=SC2016  # expanded by the container's sh
    compose exec -T caddy sh -c \
        'ls -t /data/caddy/certificates/*/"$1"/"$1".crt 2>/dev/null | head -n 1' _ "$hostname" \
        < /dev/null 2> /dev/null | tr -d '\r'
}

deadline=$((SECONDS + wait_seconds))
crt=""
while :; do
    crt=$(find_caddy_cert || true)
    [[ -n $crt ]] && break
    if ((SECONDS >= deadline)); then
        if ((wait_seconds > 0)); then
            die "caddy has no certificate for $hostname after ${wait_seconds}s; see: sudo $CLTL_ROOT/scripts/server-compose.sh logs caddy"
        fi
        log "caddy has no certificate for $hostname yet; nothing to do"
        exit 0
    fi
    sleep 5
done
key=${crt%.crt}.key

compose exec -T caddy cat "$crt" < /dev/null > "$work/full.pem"
compose exec -T caddy cat "$key" < /dev/null > "$work/key.pem"
[[ -s $work/full.pem && -s $work/key.pem ]] || die "could not read $crt from caddy"

# Leaf first, intermediates after; Erlang's ssl reads only the first
# certificate of certfile and sends the rest of the chain from cacertfile.
awk -v leaf="$work/cert.pem" -v chain="$work/chain.pem" '
    /-----BEGIN CERTIFICATE-----/ { n++ }
    { print > (n == 1 ? leaf : chain) }' "$work/full.pem"
[[ -s $work/chain.pem ]] || cp "$work/cert.pem" "$work/chain.pem"

if cmp -s "$work/cert.pem" "$CLTL_TLS_DIR/cert.pem" \
        && cmp -s "$work/chain.pem" "$CLTL_TLS_DIR/chain.pem" \
        && cmp -s "$work/key.pem" "$CLTL_TLS_DIR/key.pem"; then
    log "RabbitMQ already has caddy's current certificate for $hostname"
    exit 0
fi

install_files "$work/cert.pem" "$work/chain.pem" "$work/key.pem"
rabbitmqctl eval 'ssl:clear_pem_cache().' > /dev/null
log "RabbitMQ now serves caddy's certificate for $hostname ($(openssl x509 -noout -enddate -in "$work/cert.pem"))"

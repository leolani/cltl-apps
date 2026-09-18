#!/usr/bin/env bash
# Copy the certificate caddy obtained into a form the broker can read, and tell
# the broker to pick it up. Run it after the first `up`, and on a timer
# thereafter — see docs/operator.md for the systemd timer.
#
#   bin/sync-certs.sh
#
# Why a copy rather than a shared mount. Caddy writes the private key root-only
# inside its own data volume; RabbitMQ does not run as root and cannot read it.
# Mounting caddy's /data into the broker therefore fails at startup with a
# permission error that reads like a missing file. One ACME client, one
# certificate, and this script is the joint between them.
#
# RabbitMQ caches PEM files in the Erlang ssl app, so writing new bytes is not
# enough on its own: clear_pem_cache is what makes an existing broker serve the
# renewed certificate without dropping every student's connection.
set -euo pipefail

cd "$(dirname "$0")/.."

[[ -f .env ]] || { echo "No .env — copy .env.example and fill it in first." >&2; exit 1; }
# shellcheck disable=SC1091
set -a; source .env; set +a
: "${CLTL_HOSTNAME:?set CLTL_HOSTNAME in .env}"

COMPOSE="docker compose -f server.compose.yml"
SRC="/data/caddy/certificates/acme-v02.api.letsencrypt.org-directory/$CLTL_HOSTNAME"
DEST="secrets/tls"

mkdir -p "$DEST"

# Read them out of the running caddy container rather than guessing at a host
# path: the certificates live in a named volume, and the storage layout is
# caddy's business, not ours. If this fails, the usual cause is that caddy has
# not finished its first ACME run — `docker compose logs caddy` says so plainly.
if ! $COMPOSE exec -T caddy test -f "$SRC/$CLTL_HOSTNAME.crt"; then
    echo "No certificate for $CLTL_HOSTNAME in caddy's store yet." >&2
    echo "Check 'docker compose -f server.compose.yml logs caddy' — the ACME" >&2
    echo "challenge needs port 80 reachable and the DNS name resolving here." >&2
    exit 1
fi

$COMPOSE exec -T caddy cat "$SRC/$CLTL_HOSTNAME.crt" > "$DEST/fullchain.pem.new"
$COMPOSE exec -T caddy cat "$SRC/$CLTL_HOSTNAME.key" > "$DEST/privkey.pem.new"

# Only disturb the broker if something actually changed. On a timer that runs
# daily against a certificate that renews every sixty days, that is the
# difference between one cache flush a month and thirty.
changed=0
for f in fullchain privkey; do
    if ! cmp -s "$DEST/$f.pem.new" "$DEST/$f.pem" 2>/dev/null; then changed=1; fi
done

if [[ $changed -eq 0 ]]; then
    rm -f "$DEST"/*.pem.new
    echo "Certificate unchanged; nothing to do."
    exit 0
fi

mv "$DEST/fullchain.pem.new" "$DEST/fullchain.pem"
mv "$DEST/privkey.pem.new"   "$DEST/privkey.pem"
# World-readable certificate, key readable by the broker's uid. The key never
# leaves this host and the directory itself is 700.
chmod 644 "$DEST/fullchain.pem"
chmod 644 "$DEST/privkey.pem"

if $COMPOSE ps --status running rabbitmq | grep -q rabbitmq; then
    $COMPOSE exec -T rabbitmq rabbitmqctl eval 'ssl:clear_pem_cache().' >/dev/null
    echo "Certificate updated and the broker's PEM cache cleared."
else
    echo "Certificate updated. The broker is not running; it will read it on start."
fi

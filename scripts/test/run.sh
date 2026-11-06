#!/usr/bin/env bash
# Commands run inside the VM are single-quoted on purpose:
# shellcheck disable=SC2016
# Runs scripts/install-server.sh end to end in a throwaway Ubuntu "VM": a
# privileged systemd container with its own Docker daemon, standing in for a
# fresh cloud machine, and Pebble (Let's Encrypt's ACME test server) standing
# in for Let's Encrypt. Needs Docker on this machine and a Python with kombu.
#
#   scripts/test/run.sh [24.04|22.04]
#
# Environment:
#   PYTHON        interpreter with kombu installed (default: python3)
#   COMBOT_SRC    cltl-combot sources for bus_check.py
#                 (default: ../cltl-dev/cltl-combot/src next to this checkout)
#   KEEP=1        leave the VM running afterwards, for poking at
#
# What it checks: a first install with a tenant list, the post-install checks,
# per-tenant isolation and TLS from outside (bus_check.py), an idempotent
# re-run with no flags, add-tenant.sh, certificate rotation without a broker
# restart, a reboot, and the shared-user layout on a second install.
#
# The VM's /var/lib/docker and /var/lib/containerd are named volumes (overlay
# cannot sit on overlay), kept between runs so the images are pulled once.
set -euo pipefail

UBUNTU=${1:-24.04}
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
PYTHON=${PYTHON:-python3}
COMBOT_SRC=${COMBOT_SRC:-$ROOT/../cltl-dev/cltl-combot/src}
VM=cltl-test-vm
IMAGE=cltl-test-vm:$UBUNTU
HOST=cltl.test
PEBBLE=ghcr.io/letsencrypt/pebble:latest
WORK=$(mktemp -d)

log() { printf '\n\033[1;35m### %s\033[0m\n' "$*" >&2; }
vm() { docker exec "$VM" "$@"; }
cleanup() {
    rm -rf "$WORK"
    if [[ ${KEEP:-0} != 1 ]]; then docker rm -f "$VM" > /dev/null 2>&1 || true; fi
}
trap cleanup EXIT

failures=0
expect() {  # description command...
    local what=$1; shift
    if "$@"; then echo "PASS $what"; else echo "FAIL $what"; failures=$((failures + 1)); fi
}

boot_vm() {
    docker rm -f "$VM" > /dev/null 2>&1 || true
    docker run -d --name "$VM" --hostname cltl-vm --privileged --cgroupns=host \
        -v /sys/fs/cgroup:/sys/fs/cgroup:rw --tmpfs /run --tmpfs /run/lock \
        -v "cltl-test-docker-$UBUNTU:/var/lib/docker" \
        -v "cltl-test-containerd-$UBUNTU:/var/lib/containerd" "$IMAGE" > /dev/null
    for _ in $(seq 60); do
        state=$(vm systemctl is-system-running 2> /dev/null || true)
        [[ $state == running || $state == degraded ]] && return 0
        sleep 1
    done
    echo "VM did not boot: $state" >&2; return 1
}

copy_checkout() {  # the working tree as it is, committed or not; no config/ or storage/ state
    (cd "$ROOT" && git ls-files -co --exclude-standard -z | tar --null -T - -cf "$WORK/src.tar")
    vm mkdir -p /opt/cltl-apps
    docker cp - "$VM:/opt/cltl-apps" < "$WORK/src.tar"
}

prepare_pebble() {
    # Pebble's own TLS certificate (for its ACME directory) is signed by
    # minica; caddy must trust that to talk to it. The CA that signs the
    # certificates Pebble *issues* is generated when it starts, and fetched
    # by a poller below once it is up.
    local id
    # Pebble makes a new CA every time it starts, so a certificate caddy kept
    # from an earlier run (the VM's Docker data outlives it) would not verify.
    vm sh -c 'rm -f /opt/cltl-test/pebble-root.pem
              if command -v docker > /dev/null; then
                  docker ps -aq | xargs -r docker rm -f > /dev/null
                  docker volume ls -q | grep caddy | xargs -r docker volume rm > /dev/null
              else
                  rm -rf /var/lib/docker/volumes/*caddy*
              fi'
    docker pull -q "$PEBBLE" > /dev/null
    id=$(docker create "$PEBBLE")
    docker cp "$id:/test/certs/pebble.minica.pem" "$WORK/pebble.minica.pem"
    docker rm "$id" > /dev/null
    vm mkdir -p /opt/cltl-test /opt/cltl-apps/config
    docker cp "$WORK/pebble.minica.pem" "$VM:/opt/cltl-test/pebble.minica.pem"
    docker exec -i "$VM" sh -c 'cat > /opt/cltl-apps/config/compose.override.yml' << EOF
# Test only (scripts/test/run.sh): Pebble instead of Let's Encrypt.
services:
  pebble:
    image: $PEBBLE
    command: -config /test/config/pebble-config.json
    environment:
      PEBBLE_VA_ALWAYS_VALID: "1"
      PEBBLE_VA_NOSLEEP: "1"
    ports:
      - "127.0.0.1:15000:15000"
    networks:
      - cltl-platform
  caddy:
    environment:
      SSL_CERT_FILE: /pebble/pebble.minica.pem
    volumes:
      - /opt/cltl-test/pebble.minica.pem:/pebble/pebble.minica.pem:ro
EOF
    vm sh -c 'nohup sh -c "until curl -sfk https://127.0.0.1:15000/roots/0 -o /opt/cltl-test/root.tmp; do sleep 2; done; mv /opt/cltl-test/root.tmp /opt/cltl-test/pebble-root.pem" > /dev/null 2>&1 &'
}

install() {
    vm /opt/cltl-apps/scripts/install-server.sh --no-pull --skip-dns-check \
        --acme-ca https://pebble:14000/dir --test-ca-file /opt/cltl-test/pebble-root.pem "$@"
}

issuer_matches() {  # pattern
    vm sh -c "openssl s_client -connect 127.0.0.1:5671 -servername $HOST < /dev/null 2> /dev/null \
              | openssl x509 -noout -issuer" | grep -q "$1"
}

log "Building the Ubuntu $UBUNTU VM image"
docker build -q --build-arg "UBUNTU=$UBUNTU" -t "$IMAGE" "$HERE" > /dev/null
boot_vm
VM_IP=$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' "$VM")
copy_checkout
prepare_pebble
printf '# test tenants\ntenant-a\ntenant-b  # second\n' | docker exec -i "$VM" sh -c 'cat > /opt/cltl-test/tenants.txt'

log "First install, with a tenant list"
install --hostname "$HOST" --email ops@cltl.test --tenants /opt/cltl-test/tenants.txt
expect "cltl-server.service active" vm systemctl is-active -q cltl-server.service
expect "cert timer active" vm systemctl is-active -q cltl-rabbitmq-cert.timer
expect "tenants.urls lists tenant-a and tenant-b" \
    vm sh -c 'grep -q "^tenant-a amqps://tenant-a:" /opt/cltl-apps/config/tenants.urls \
              && grep -q "^tenant-b amqps://tenant-b:" /opt/cltl-apps/config/tenants.urls'
expect "secrets are root-only" \
    vm sh -c 'test "$(stat -c %a /opt/cltl-apps/config/credentials /opt/cltl-apps/config/tenants.urls | sort -u)" = 600'
expect "AMQPS serves Pebble's certificate" issuer_matches Pebble

docker cp "$VM:/opt/cltl-test/pebble-root.pem" "$WORK/ca.pem"
docker cp "$VM:/opt/cltl-apps/config/tenants.urls" "$WORK/tenants.urls"

log "From outside: TLS, isolation, closed ports"
expect "bus_check.py" env PYTHONPATH="$COMBOT_SRC" "$PYTHON" "$HERE/bus_check.py" \
    "$VM_IP" "$HOST" "$WORK/ca.pem" "$WORK/tenants.urls"
for port in 8001 8002 15672; do
    expect "port $port closed from outside" sh -c "! (exec 3<>/dev/tcp/$VM_IP/$port) 2> /dev/null"
done
expect "https://$HOST/storage/ needs Basic Auth" sh -c \
    "test \"\$(curl -s -o /dev/null -w '%{http_code}' --cacert $WORK/ca.pem --resolve $HOST:443:$VM_IP https://$HOST/storage/)\" = 401"

admin_pw=$(vm sh -c "grep ^RABBITMQ_ADMIN_PASSWORD= /opt/cltl-apps/config/credentials | cut -d= -f2")
expect "RabbitMQ management API works through caddy with the admin's own login" sh -c \
    "test \"\$(curl -s -o /dev/null -w '%{http_code}' --cacert $WORK/ca.pem --resolve $HOST:443:$VM_IP \
           -u eliza:$admin_pw https://$HOST/rabbitmq/api/whoami)\" = 200"
tenant_a=$(awk '$1 == "tenant-a" { print $2 }' "$WORK/tenants.urls" | sed -E 's#^amqps://[^:]*:([^@]*)@.*#\1#')
expect "a tenant user cannot use the management API" sh -c \
    "test \"\$(curl -s -o /dev/null -w '%{http_code}' --cacert $WORK/ca.pem --resolve $HOST:443:$VM_IP \
           -u tenant-a:$tenant_a https://$HOST/rabbitmq/api/whoami)\" = 401"

log "Re-run with no flags: same secrets, same tenants"
before=$(vm sha256sum /opt/cltl-apps/config/credentials /opt/cltl-apps/config/tenants.urls)
install
after=$(vm sha256sum /opt/cltl-apps/config/credentials /opt/cltl-apps/config/tenants.urls)
expect "credentials and tenants.urls unchanged" test "$before" = "$after"

log "add-tenant.sh"
vm /opt/cltl-apps/scripts/add-tenant.sh tenant-c
docker cp "$VM:/opt/cltl-apps/config/tenants.urls" "$WORK/tenants.urls"
expect "tenant-c added, a and b kept" sh -c "grep -c '^tenant-[abc] ' $WORK/tenants.urls | grep -qx 3"
expect "bus_check.py with tenant-c" env PYTHONPATH="$COMBOT_SRC" "$PYTHON" "$HERE/bus_check.py" \
    "$VM_IP" "$HOST" "$WORK/ca.pem" "$WORK/tenants.urls"

log "Certificate rotation without restarting RabbitMQ"
started=$(vm docker inspect -f '{{.State.StartedAt}}' cltl-platform-rabbitmq-1)
vm sh -c 'rm -f /opt/cltl-apps/storage/rabbitmq-tls/*.pem && /opt/cltl-apps/scripts/sync-rabbitmq-cert.sh --seed \
          && /opt/cltl-apps/scripts/server-compose.sh exec -T rabbitmq rabbitmqctl -q eval "ssl:clear_pem_cache()."' > /dev/null
expect "a replaced certificate is served at once" issuer_matches "CN *= *$HOST"
vm /opt/cltl-apps/scripts/sync-rabbitmq-cert.sh
expect "sync puts caddy's certificate back" issuer_matches Pebble
expect "RabbitMQ was not restarted" test "$started" = "$(vm docker inspect -f '{{.State.StartedAt}}' cltl-platform-rabbitmq-1)"

log "Reboot"
docker restart "$VM" > /dev/null
for _ in $(seq 120); do
    vm systemctl is-active -q cltl-server.service 2> /dev/null && break
    sleep 5
done
expect "cltl-server.service active after reboot" vm systemctl is-active -q cltl-server.service
VM_IP=$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' "$VM")
expect "bus_check.py after reboot" env PYTHONPATH="$COMBOT_SRC" "$PYTHON" "$HERE/bus_check.py" \
    "$VM_IP" "$HOST" "$WORK/ca.pem" "$WORK/tenants.urls"

log "Second install without a tenant list: one shared user"
vm sh -c 'systemctl disable -q --now cltl-server.service cltl-rabbitmq-cert.timer; rm -rf /opt/cltl-apps'
copy_checkout
prepare_pebble
install --hostname "$HOST" --email ops@cltl.test
docker cp "$VM:/opt/cltl-test/pebble-root.pem" "$WORK/ca.pem"
docker cp "$VM:/opt/cltl-apps/config/tenants.urls" "$WORK/tenants.urls"
expect "only the shared tenant user" sh -c "grep -v '^#' $WORK/tenants.urls | cut -d' ' -f1 | paste -sd, | grep -qx tenant"
expect "bus_check.py with the shared user" env PYTHONPATH="$COMBOT_SRC" "$PYTHON" "$HERE/bus_check.py" \
    "$VM_IP" "$HOST" "$WORK/ca.pem" "$WORK/tenants.urls"

log "Done: $failures failure(s)"
((failures == 0))

#!/usr/bin/env bash
# Installs and starts a public cltl-apps SERVER deployment on Ubuntu 22.04 or
# 24.04: the server role (templates/server) behind modules/reverse-proxy, with
# TLS and auth on everything reachable from outside. See
# doc/DEPLOYMENT.md#installing-a-server-on-a-cloud-vm.
#
# On a fresh machine:
#
#   curl -fsSL https://raw.githubusercontent.com/leolani/cltl-apps/main/scripts/install-server.sh \
#       | sudo bash -s -- --hostname combot.example.org --email you@example.org
#
# or, from a checkout:
#
#   sudo scripts/install-server.sh --hostname combot.example.org --email you@example.org
#
# Options:
#   --hostname NAME    DNS name of this machine; must already resolve to it,
#                      with port 80 reachable (Let's Encrypt). Required once.
#   --email ADDRESS    contact address for the ACME account. Required once.
#   --tenants FILE     tenant ids, one per line (# comments allowed): one
#                      RabbitMQ user each, confined to its own routing keys.
#                      Without it, and with no tenants yet, a single shared
#                      user `tenant` is created instead.
#   --auth-user NAME   Basic Auth user for /storage and /emissor
#                      (default: cltl; the password is generated)
#   --version TAG      image tag for every ghcr.io/leolani image (default: latest)
#   --dir PATH         where to clone when not run from a checkout
#                      (default: /opt/cltl-apps)
#   --repo URL         repository to clone (default: github.com/leolani/cltl-apps)
#   --ref REF          branch or tag to clone (default: main)
#   --no-pull          do not `git pull` an existing checkout
#
# Run it again at any time to upgrade (pulls the checkout and the images,
# then restarts) or to add tenants from an extended --tenants file. Every
# value given once is remembered in config/; secrets are generated once and
# never rotated.
#
# Writes: config/server.env, config/custom.config (from the templates, plus
# the event bus's admin password), config/credentials, config/basic-auth.auth,
# config/tenants.urls, storage/rabbitmq-tls/, and the systemd units
# cltl-server.service and cltl-rabbitmq-cert.{service,timer}.
#
# Testing only (scripts/test/): --acme-ca URL, --test-ca-file PEM (trust
# for the post-install checks), --skip-dns-check.
set -euo pipefail

DEFAULT_REPO=https://github.com/leolani/cltl-apps.git

hostname_arg="" email_arg="" tenants_arg="" auth_user_arg="" version_arg=""
dir=/opt/cltl-apps repo=$DEFAULT_REPO ref=main pull=1
acme_ca_arg="" test_ca_file="" skip_dns_check=0
original_args=("$@")
start_dir=$PWD

usage() { sed -n '2,46p' "${BASH_SOURCE[0]}" 2> /dev/null | sed 's/^# \{0,1\}//'; }

while [[ $# -gt 0 ]]; do
    case $1 in
        --hostname) hostname_arg=${2:?}; shift ;;
        --email) email_arg=${2:?}; shift ;;
        --tenants) tenants_arg=${2:?}; shift ;;
        --auth-user) auth_user_arg=${2:?}; shift ;;
        --version) version_arg=${2:?}; shift ;;
        --dir) dir=${2:?}; shift ;;
        --repo) repo=${2:?}; shift ;;
        --ref) ref=${2:?}; shift ;;
        --no-pull) pull=0 ;;
        --acme-ca) acme_ca_arg=${2:?}; shift ;;
        --test-ca-file) test_ca_file=${2:?}; shift ;;
        --skip-dns-check) skip_dns_check=1 ;;
        -h|--help) usage; exit 0 ;;
        *) echo "unknown option: $1 (see --help)" >&2; exit 2 ;;
    esac
    shift
done

[[ $EUID -eq 0 ]] || { echo "run as root: sudo $0 ..." >&2; exit 1; }

# A tenant file named on the command line is relative to where we were run,
# not to the checkout we cd into below.
if [[ -n $tenants_arg ]]; then
    [[ -r $tenants_arg ]] || { echo "cannot read tenant list $tenants_arg" >&2; exit 1; }
    tenants_arg=$(realpath "$tenants_arg")
fi
[[ -z $test_ca_file ]] || test_ca_file=$(realpath "$test_ca_file")

export DEBIAN_FRONTEND=noninteractive

apt_install() {
    local missing=() pkg
    for pkg in "$@"; do
        dpkg-query -W -f='${Status}' "$pkg" 2> /dev/null | grep -q "install ok installed" || missing+=("$pkg")
    done
    [[ ${#missing[@]} -eq 0 ]] && return 0
    echo "==> Installing ${missing[*]}" >&2
    apt-get update -q
    apt-get install -y -q --no-install-recommends "${missing[@]}"
}

apt_install ca-certificates curl git openssl dnsutils iproute2

# --- 1. Bootstrap: find or make the checkout, then run from inside it ----------

self=${BASH_SOURCE[0]:-}
self_root=""
if [[ -n $self && -f $self ]]; then
    self_root=$(cd "$(dirname "$self")/.." && pwd)
    [[ -f $self_root/modules/event-bus/docker-compose.yml ]] || self_root=""
fi

if [[ -z $self_root ]]; then
    # Piped from curl, or copied out of a checkout: clone one and re-run the
    # script from it, so what runs always matches the modules it installs.
    if [[ -d $dir/.git ]]; then
        echo "==> Updating $dir to $ref" >&2
        git -c safe.directory="$dir" -C "$dir" fetch -q origin "$ref"
        git -c safe.directory="$dir" -C "$dir" checkout -q "$ref"
        git -c safe.directory="$dir" -C "$dir" merge -q --ff-only "origin/$ref" 2> /dev/null || true
    else
        [[ ! -e $dir ]] || { echo "$dir exists and is not a checkout" >&2; exit 1; }
        echo "==> Cloning $repo ($ref) into $dir" >&2
        git clone -q --branch "$ref" "$repo" "$dir"
    fi
    exec "$dir/scripts/install-server.sh" "${original_args[@]}" --no-pull
fi

CLTL_ROOT=$self_root
cd "$CLTL_ROOT"
# shellcheck source=scripts/common.sh
source "$CLTL_ROOT/scripts/common.sh"

if ((pull)); then
    if [[ -n $(git -c safe.directory="$CLTL_ROOT" status --porcelain --untracked-files=no) ]]; then
        warn "the checkout has local changes; not pulling"
    elif git -c safe.directory="$CLTL_ROOT" symbolic-ref -q HEAD > /dev/null; then
        log "Updating the checkout"
        if git -c safe.directory="$CLTL_ROOT" pull -q --ff-only; then
            # The pulled script may differ from the one running; run that one,
            # from where we started, so relative paths in the arguments hold.
            cd "$start_dir"
            exec "$CLTL_ROOT/scripts/install-server.sh" "${original_args[@]}" --no-pull
        fi
        warn "git pull failed; continuing with the checkout as it is"
    fi
fi

# --- 2. Preflight ----------------------------------------------------------------

# shellcheck disable=SC1091
. /etc/os-release
if [[ ${ID:-} != ubuntu || ! ${VERSION_ID:-} =~ ^(22\.04|24\.04)$ ]]; then
    warn "tested on Ubuntu 22.04 and 24.04 only; this is ${PRETTY_NAME:-unknown}"
fi
free_gb=$(df -P --block-size=1G "$CLTL_ROOT" | awk 'NR == 2 { print $4 }')
mem_gb=$(awk '/^MemTotal:/ { printf "%d", $2 / 1024 / 1024 }' /proc/meminfo)
((free_gb >= 20)) || warn "${free_gb} GB free disk; the images and the Whisper model need about 20 GB"
((mem_gb >= 7)) || warn "${mem_gb} GB RAM; 8 GB or more is recommended"

# --- 3. Docker ---------------------------------------------------------------------

if ! docker compose version > /dev/null 2>&1; then
    log "Installing Docker Engine and the Compose plugin from download.docker.com"
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
    chmod a+r /etc/apt/keyrings/docker.asc
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc]" \
         "https://download.docker.com/linux/ubuntu ${UBUNTU_CODENAME:-$VERSION_CODENAME} stable" \
         > /etc/apt/sources.list.d/docker.list
    apt-get update -q
    apt-get install -y -q docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
    systemctl enable --now docker
fi
docker compose version > /dev/null || die "docker compose does not work"

# --- 4. Inputs, remembered across runs --------------------------------------------

mkdir -p config
if [[ ! -f config/default.config ]]; then
    log "Populating config/ from templates/common and templates/server"
    cp templates/common/config/* config/
fi
[[ -f config/custom.config ]] || cp templates/server/config/custom.config config/
[[ -f config/server.env ]] || cp templates/server/config/server.env config/
chmod 600 config/server.env
touch "$CLTL_CREDENTIALS_FILE"
chmod 600 "$CLTL_CREDENTIALS_FILE"

pick() {  # flag value, else stored value
    if [[ -n $1 ]]; then printf '%s' "$1"; else kv_get "$2" "$3"; fi
}
hostname=$(pick "$hostname_arg" "$CLTL_ENV_FILE" CLTL_HOSTNAME)
email=$(pick "$email_arg" "$CLTL_ENV_FILE" CLTL_ACME_EMAIL)
version=$(pick "$version_arg" "$CLTL_ENV_FILE" VERSION)
acme_ca=$(pick "$acme_ca_arg" "$CLTL_ENV_FILE" CLTL_ACME_CA)
auth_user=$(pick "$auth_user_arg" "$CLTL_CREDENTIALS_FILE" BASIC_AUTH_USER)
auth_user=${auth_user:-cltl}

[[ -n $hostname ]] || die "--hostname is required on the first run (see --help)"
[[ -n $email ]] || die "--email is required on the first run (see --help)"
[[ $hostname =~ ^[A-Za-z0-9.-]+$ ]] || die "invalid hostname '$hostname'"
[[ $auth_user =~ ^[A-Za-z0-9._-]+$ ]] || die "invalid --auth-user '$auth_user'"

admin_password=$(kv_get "$CLTL_CREDENTIALS_FILE" RABBITMQ_ADMIN_PASSWORD)
auth_password=$(kv_get "$CLTL_CREDENTIALS_FILE" BASIC_AUTH_PASSWORD)
[[ -n $admin_password ]] || admin_password=$(generate_secret)
[[ -n $auth_password ]] || auth_password=$(generate_secret)

kv_set "$CLTL_CREDENTIALS_FILE" RABBITMQ_ADMIN_USER "$CLTL_RABBITMQ_ADMIN"
kv_set "$CLTL_CREDENTIALS_FILE" RABBITMQ_ADMIN_PASSWORD "$admin_password"
kv_set "$CLTL_CREDENTIALS_FILE" BASIC_AUTH_USER "$auth_user"
kv_set "$CLTL_CREDENTIALS_FILE" BASIC_AUTH_PASSWORD "$auth_password"

# --- 5. Config ----------------------------------------------------------------------

kv_set "$CLTL_ENV_FILE" CLTL_HOSTNAME "$hostname"
kv_set "$CLTL_ENV_FILE" CLTL_ACME_EMAIL "$email"
[[ -z $version ]] || kv_set "$CLTL_ENV_FILE" VERSION "$version"
[[ -z $acme_ca ]] || kv_set "$CLTL_ENV_FILE" CLTL_ACME_CA "$acme_ca"
kv_set "$CLTL_ENV_FILE" CLTL_RABBITMQ_PASS "$admin_password"
# Only caddy (80, 443) and AMQPS (5671) face outward. The modules' own ports
# stay on loopback for an operator on this machine.
for var in CLTL_STORAGE_BIND CLTL_EMISSOR_BIND CLTL_RABBITMQ_MGMT_BIND CLTL_AMQP_BIND; do
    kv_set "$CLTL_ENV_FILE" "$var" 127.0.0.1
done

# The modules here reach the broker on the Docker network, as the admin.
ini_set config/custom.config cltl.event.kombu server "amqp://$CLTL_RABBITMQ_ADMIN:$admin_password@rabbitmq:5672/"

if [[ ! -s config/basic-auth.auth || $(awk '{ print $1; exit }' config/basic-auth.auth) != "$auth_user" ]]; then
    log "Writing the Basic Auth credential for $auth_user"
    hash=$(docker run --rm caddy:2.8-alpine caddy hash-password --plaintext "$auth_password")
    (umask 077 && printf '%s %s\n' "$auth_user" "$hash" > config/basic-auth.auth)
fi
# caddy reads it as a non-root file inside its container; it holds a hash only.
chmod 644 config/basic-auth.auth

# --- 6. DNS ---------------------------------------------------------------------------

public_ip() {
    local url ip
    for url in https://api.ipify.org https://ifconfig.me/ip https://icanhazip.com; do
        ip=$(curl -fsS -4 -m 5 "$url" 2> /dev/null | tr -d '[:space:]') || continue
        [[ $ip =~ ^[0-9]+(\.[0-9]+){3}$ ]] && { printf '%s' "$ip"; return 0; }
    done
    return 1
}

if ((skip_dns_check)); then
    warn "skipping the DNS check"
else
    resolved=$(dig +short A "$hostname" | grep -E '^[0-9.]+$' || true)
    [[ -n $resolved ]] || die "$hostname does not resolve. Point an A record at this machine first;" \
                              "Let's Encrypt validates it over port 80."
    ip=$(public_ip || true)
    if [[ -z $ip ]]; then
        warn "could not determine this machine's public IP; trusting that $hostname ($resolved) is this machine"
    elif ! grep -qxF "$ip" <<< "$resolved"; then
        die "$hostname resolves to $(echo "$resolved" | paste -sd ' '), but this machine's public IP is $ip"
    fi
fi

# --- 7. Images, broker, users ----------------------------------------------------------

"$CLTL_ROOT/scripts/sync-rabbitmq-cert.sh" --seed

log "Pulling images (first run: several GB)"
compose pull -q

# The broker on its own first, so every user (and a changed admin password
# on an existing storage/rabbitmq) is in place before any module connects.
log "Starting the event bus"
compose up -d --wait rabbitmq
log "Setting up RabbitMQ users"
ensure_rabbitmq_user "$CLTL_RABBITMQ_ADMIN" "$admin_password"

if [[ -n $tenants_arg ]]; then
    ids=$(read_tenant_file "$tenants_arg")
    [[ -n $ids ]] || die "$tenants_arg lists no tenants"
elif [[ -n $(tenant_ids) ]]; then
    ids=$(tenant_ids)
else
    ids=$CLTL_SHARED_TENANT_USER
fi
reconcile_tenants "$hostname" "$ids"

# --- 8. systemd ---------------------------------------------------------------------------

log "Installing systemd units"
cat > /etc/systemd/system/cltl-server.service << EOF
# Installed by $CLTL_ROOT/scripts/install-server.sh
[Unit]
Description=cltl-apps server deployment ($CLTL_ROOT)
Requires=docker.service
After=docker.service network-online.target
Wants=network-online.target

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=$CLTL_ROOT
ExecStartPre=$CLTL_ROOT/scripts/sync-rabbitmq-cert.sh --seed
# Images are pulled by the installer; a boot must not depend on the registry.
ExecStart=$CLTL_ROOT/scripts/server-compose.sh up -d --wait --pull missing
ExecStop=$CLTL_ROOT/scripts/server-compose.sh down
TimeoutStartSec=30min

[Install]
WantedBy=multi-user.target
EOF

cat > /etc/systemd/system/cltl-rabbitmq-cert.service << EOF
# Installed by $CLTL_ROOT/scripts/install-server.sh
[Unit]
Description=Copy caddy's certificate to RabbitMQ's AMQPS listener
After=cltl-server.service
Requisite=cltl-server.service

[Service]
Type=oneshot
ExecStart=$CLTL_ROOT/scripts/sync-rabbitmq-cert.sh
EOF

cat > /etc/systemd/system/cltl-rabbitmq-cert.timer << EOF
# Installed by $CLTL_ROOT/scripts/install-server.sh
[Unit]
Description=Daily sync of caddy's certificate to RabbitMQ

[Timer]
OnCalendar=daily
RandomizedDelaySec=1h
Persistent=true

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable -q cltl-server.service cltl-rabbitmq-cert.timer
log "Starting the deployment (first run: ASR downloads its Whisper model)"
systemctl restart cltl-server.service
systemctl start cltl-rabbitmq-cert.timer

# --- 9. Certificate ---------------------------------------------------------------------

log "Waiting for caddy's certificate for $hostname"
"$CLTL_ROOT/scripts/sync-rabbitmq-cert.sh" --wait 300

# --- 10. Checks -----------------------------------------------------------------------------

failures=0
fail() { warn "$*"; failures=$((failures + 1)); }

backend_port=$(kv_get "$CLTL_ENV_FILE" CLTL_BACKEND_PORT)
for port in 5672 "${backend_port:-8001}" 8002 15672; do
    exposed=$(ss -ltnH "sport = :$port" | awk '{ print $4 }' | grep -vE '^(127\.0\.0\.1|\[::1\]):' || true)
    [[ -z $exposed ]] || fail "port $port listens on $(echo "$exposed" | paste -sd ' '), not loopback only"
done

curl_ca=() openssl_ca=()
if [[ -n $test_ca_file ]]; then
    curl_ca=(--cacert "$test_ca_file")
    openssl_ca=(-CAfile "$test_ca_file")
fi
status=$(curl -s -o /dev/null -w '%{http_code}' "${curl_ca[@]}" \
         --resolve "$hostname:443:127.0.0.1" "https://$hostname/storage/" || true)
[[ $status == 401 ]] || fail "https://$hostname/storage/ without credentials: HTTP $status, expected 401"
status=$(curl -s -o /dev/null -w '%{http_code}' "${curl_ca[@]}" -u "$auth_user:$auth_password" \
         --resolve "$hostname:443:127.0.0.1" "https://$hostname/storage/" || true)
[[ $status =~ ^[234][0-9][0-9]$ && $status != 401 && $status != 403 ]] \
    || fail "https://$hostname/storage/ with credentials: HTTP $status"

if ! openssl s_client -connect 127.0.0.1:5671 -servername "$hostname" -verify_hostname "$hostname" \
        -verify_return_error "${openssl_ca[@]}" < /dev/null > /dev/null 2>&1; then
    fail "AMQPS on 5671 does not present a valid certificate for $hostname"
fi

# --- 11. Summary --------------------------------------------------------------------------------

cat << EOF

cltl-apps server on https://$hostname

  Storage API       https://$hostname/storage/
  EMISSOR data API  https://$hostname/emissor/
  RabbitMQ UI       https://$hostname/rabbitmq/   (RabbitMQ's own login: $CLTL_RABBITMQ_ADMIN)
  Basic Auth        $auth_user / $auth_password
  RabbitMQ admin    $CLTL_RABBITMQ_ADMIN / $admin_password
  Event bus         amqps://$hostname:5671/

  Tenant URLs       $CLTL_TENANTS_URLS
  All secrets       $CLTL_CREDENTIALS_FILE

The cloud security group must allow inbound TCP 80, 443 and 5671.
Add a tenant:       sudo $CLTL_ROOT/scripts/add-tenant.sh <id>
Operate:            sudo $CLTL_ROOT/scripts/server-compose.sh ps|logs|...
Upgrade:            sudo $CLTL_ROOT/scripts/install-server.sh
EOF

if ((failures)); then
    die "$failures post-install check(s) failed; see the warnings above"
fi

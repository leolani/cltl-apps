# shellcheck shell=bash disable=SC2034
# Shared by the scripts in scripts/. Sourced, never run; expects CLTL_ROOT to
# be the checkout's root and the caller to have `set -euo pipefail`.
#
# The checkout belongs to the user who installed it, and everything here runs
# as that user except what needs root: packages, systemd, /etc, and the
# certificate files RabbitMQ (uid 999) reads. Those go through as_root.
#
# State this checkout keeps, all under the gitignored config/:
#   config/server.env     Compose-time values (hostname, binds, the event
#                         bus's admin password, which RabbitMQ itself needs)
#   config/credentials    every generated secret, KEY=VALUE, owner-only. Not
#                         named credentials.config on purpose: the platform's
#                         loader reads config/credentials.config into every
#                         module's configuration.
#   config/tenants.urls   one `<id> amqps://<id>:<password>@<host>:5671/` line
#                         per tenant user, owner-only; the passwords live here
#                         and nowhere else.
#   config/install.state  what the installer decided once and must decide the
#                         same way on a re-run (where Docker keeps its data).

CLTL_ENV_FILE="$CLTL_ROOT/config/server.env"
CLTL_CREDENTIALS_FILE="$CLTL_ROOT/config/credentials"
CLTL_TENANTS_URLS="$CLTL_ROOT/config/tenants.urls"
CLTL_STATE_FILE="$CLTL_ROOT/config/install.state"
CLTL_TLS_DIR="$CLTL_ROOT/storage/rabbitmq-tls"

# The shared tenant user, created when the installer is given no tenant list.
# Reserved: a tenant list may not use it (or the admin user) as an id.
CLTL_SHARED_TENANT_USER=tenant
CLTL_RABBITMQ_ADMIN=eliza

# What any tenant user may touch: the platform's one exchange, and the
# exclusive, broker-named queue each subscriber declares
# (cltl.combot.infra.event.kombu._EventBusConsumer).
CLTL_TENANT_RESOURCES='^(cltl\.combot|amq\.gen-.*)$'
# Topic permissions for a per-tenant user: it may publish, and bind its queue,
# only on routing keys ending in its own id. A tenanted module publishes and
# binds `<topic>.<tenant>`; RabbitMQ expands {username} itself.
CLTL_TENANT_TOPICS='^.+\.{username}$'

log() { printf '\033[1;34m==>\033[0m %s\n' "$*" >&2; }
warn() { printf '\033[1;33mWARNING:\033[0m %s\n' "$*" >&2; }
die() { printf '\033[1;31mERROR:\033[0m %s\n' "$*" >&2; exit 1; }

require_root() {
    [[ $EUID -eq 0 ]] || die "run as root (sudo $0 ...)"
}

require_owner() {
    # Run as anyone else, a script here would leave files in config/ that
    # their owner can no longer rewrite.
    local owner
    owner=$(stat -c %U "$CLTL_ROOT")
    [[ $(id -un) == "$owner" ]] || die "run this as $owner, who owns $CLTL_ROOT (not with sudo)"
}

as_root() {
    if [[ $EUID -eq 0 ]]; then "$@"; else sudo "$@"; fi
}

docker_cli() {
    # Right after the installer adds the user to the docker group, their
    # login session does not have it yet; sudo bridges that until they log in
    # again. The systemd unit gets the group itself.
    if [[ $EUID -ne 0 && -z ${DOCKER_HOST:-} && -S /var/run/docker.sock && ! -w /var/run/docker.sock ]]; then
        sudo docker "$@"
    else
        docker "$@"
    fi
}

generate_secret() {
    # Hex: safe unquoted in a URL, an INI value and a Compose env file (which
    # would otherwise interpolate a `$`).
    openssl rand -hex 24
}

# --- KEY=VALUE files (server.env, credentials) -------------------------------

kv_get() {  # file key -> value of the last active `key=` line, or nothing
    local file=$1 key=$2
    [[ -f $file ]] || return 0
    grep -E "^${key}=" "$file" | tail -n 1 | cut -d= -f2- || true
}

kv_set() {  # file key value: replace the active line, or append one
    local file=$1 key=$2 value=$3
    touch "$file"
    if grep -qE "^${key}=" "$file"; then
        awk -v k="$key" -v v="$value" '
            BEGIN { done = 0 }
            index($0, k "=") == 1 && !done { print k "=" v; done = 1; next }
            index($0, k "=") == 1 { next }
            { print }' "$file" > "$file.tmp"
        cat "$file.tmp" > "$file" && rm -f "$file.tmp"
    else
        printf '%s=%s\n' "$key" "$value" >> "$file"
    fi
}

# --- INI (custom.config) ------------------------------------------------------

ini_set() {  # file section key value: set key in [section], adding either
    local file=$1 section=$2 key=$3 value=$4
    awk -v s="[$section]" -v k="$key" -v v="$value" '
        function flush() { if (in_s && !done) { print k ": " v; done = 1 } }
        /^\[.*\][[:space:]]*$/ {
            flush()
            in_s = ($0 ~ "^\\[" ) && (substr($0, 1, length(s)) == s)
            print; next
        }
        in_s && !done && $0 ~ "^" k "[[:space:]]*[:=]" { print k ": " v; done = 1; next }
        { print }
        END {
            flush()
            if (!done) { print ""; print s; print k ": " v }
        }' "$file" > "$file.tmp"
    cat "$file.tmp" > "$file" && rm -f "$file.tmp"
}

# --- docker compose / rabbitmqctl ---------------------------------------------

compose() {
    "$CLTL_ROOT/scripts/server-compose.sh" "$@"
}

rabbitmqctl() {
    # Never the caller's stdin: `exec -T` forwards it, and inside a
    # `while read` loop that swallows the rest of the loop's input.
    compose exec -T rabbitmq rabbitmqctl --quiet "$@" < /dev/null
}

rabbitmq_users() {
    rabbitmqctl list_users --no-table-headers | awk '{ print $1 }'
}

# --- tenant users ---------------------------------------------------------------

validate_tenant_id() {
    local id=$1
    [[ $id =~ ^[a-z0-9][a-z0-9_-]*$ ]] \
        || die "invalid tenant id '$id': lower-case letters, digits, '-' and '_' only, no dots" \
               "(the tenant must be the last word of a routing key)"
    [[ $id != "$CLTL_SHARED_TENANT_USER" && $id != "$CLTL_RABBITMQ_ADMIN" ]] \
        || die "tenant id '$id' is reserved"
}

read_tenant_file() {  # file -> one id per line, comments and blanks dropped
    local file=$1 line
    [[ -r $file ]] || die "cannot read tenant list $file"
    while IFS= read -r line || [[ -n $line ]]; do
        line=${line%%#*}
        line=$(printf '%s' "$line" | tr -d '[:space:]')
        [[ -z $line ]] && continue
        validate_tenant_id "$line"
        printf '%s\n' "$line"
    done < "$file" | awk '!seen[$0]++'
}

tenant_password() {  # id -> stored password, or nothing
    local id=$1
    [[ -f $CLTL_TENANTS_URLS ]] || return 0
    awk -v id="$id" '$1 == id { print $2 }' "$CLTL_TENANTS_URLS" \
        | sed -E 's#^amqps?://[^:]*:([^@]*)@.*#\1#' | tail -n 1
}

tenant_ids() {  # ids already in tenants.urls
    [[ -f $CLTL_TENANTS_URLS ]] || return 0
    awk 'NF >= 2 && $1 !~ /^#/ { print $1 }' "$CLTL_TENANTS_URLS"
}

ensure_rabbitmq_user() {  # user password: create, or enforce the password
    local user=$1 password=$2
    if rabbitmq_users | grep -qxF "$user"; then
        rabbitmqctl change_password "$user" "$password" > /dev/null
    else
        rabbitmqctl add_user "$user" "$password" > /dev/null
    fi
}

ensure_tenant_user() {  # id password
    local id=$1 password=$2
    ensure_rabbitmq_user "$id" "$password"
    # No tags: no management UI, no administration.
    rabbitmqctl set_user_tags "$id" > /dev/null
    rabbitmqctl set_permissions -p / "$id" \
        "$CLTL_TENANT_RESOURCES" "$CLTL_TENANT_RESOURCES" "$CLTL_TENANT_RESOURCES" > /dev/null
    if [[ $id == "$CLTL_SHARED_TENANT_USER" ]]; then
        # Shared by every tenant, so it cannot be confined to one routing key:
        # separation between tenants stays cooperative, as without users.
        rabbitmqctl clear_topic_permissions -p / "$id" > /dev/null 2>&1 || true
    else
        rabbitmqctl set_topic_permissions -p / "$id" cltl.combot \
            "$CLTL_TENANT_TOPICS" "$CLTL_TENANT_TOPICS" > /dev/null
    fi
}

write_tenants_urls() {  # hostname, then `id password` pairs on stdin
    local hostname=$1 id password
    (
    umask 077
    {
        echo "# Generated by scripts/install-server.sh / scripts/add-tenant.sh."
        echo "# One RabbitMQ user per line; paste the URL into that tenant's"
        echo "# config/custom.config as [cltl.event.kombu] server."
        while read -r id password; do
            printf '%s amqps://%s:%s@%s:5671/\n' "$id" "$id" "$password" "$hostname"
        done
    } > "$CLTL_TENANTS_URLS.tmp"
    )
    mv "$CLTL_TENANTS_URLS.tmp" "$CLTL_TENANTS_URLS"
    chmod 600 "$CLTL_TENANTS_URLS"
}

# Create or update every user in `ids` (one per line) and rewrite
# tenants.urls with those plus every tenant already in it. Never deletes.
reconcile_tenants() {  # hostname ids
    local hostname=$1 ids=$2 id password pairs=""
    local all
    all=$(printf '%s\n%s\n' "$(tenant_ids)" "$ids" | awk 'NF && !seen[$0]++')

    while IFS= read -r id; do
        [[ -z $id ]] && continue
        password=$(tenant_password "$id")
        [[ -n $password ]] || password=$(generate_secret)
        if printf '%s\n' "$ids" | grep -qxF "$id"; then
            ensure_tenant_user "$id" "$password"
        fi
        pairs+="$id $password"$'\n'
    done <<< "$all"

    printf '%s' "$pairs" | write_tenants_urls "$hostname"

    local extra
    extra=$(rabbitmq_users | grep -vxF "$CLTL_RABBITMQ_ADMIN" | grep -vxF -f <(printf '%s\n' "$all") || true)
    if [[ -n $extra ]]; then
        while IFS= read -r id; do
            warn "RabbitMQ user '$id' is not in config/tenants.urls; left in place." \
                 "Remove it with: $CLTL_ROOT/scripts/server-compose.sh exec rabbitmq rabbitmqctl delete_user $id"
        done <<< "$extra"
    fi
    local listed
    listed=$(tenant_ids)
    if [[ -n $ids ]] && ! printf '%s\n' "$ids" | grep -qxF "$CLTL_SHARED_TENANT_USER" \
            && printf '%s\n' "$listed" | grep -qxF "$CLTL_SHARED_TENANT_USER"; then
        warn "the shared '$CLTL_SHARED_TENANT_USER' user still exists alongside per-tenant users;" \
             "it is not confined to one tenant. Remove it with rabbitmqctl delete_user $CLTL_SHARED_TENANT_USER" \
             "and its line in config/tenants.urls once no tenant uses it."
    fi
}

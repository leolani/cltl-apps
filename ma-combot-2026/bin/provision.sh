#!/usr/bin/env bash
# Create one broker user and one storage credential per student, from the
# roster, and write each student a connection sheet.
#
#   bin/provision.sh roster.csv
#
# Idempotent by design: run it again after adding a line to the roster and only
# the new students are touched. Existing passwords are kept — re-running must
# not silently invalidate credentials people are already using. Use
# bin/reissue.sh for the one student who lost theirs.
#
# What this establishes is TRACEABILITY, not isolation. Permissions are
# deliberately permissive: any student can read any tenant's traffic and publish
# into it, exactly as custom-module/docs/tenancy.md describes. The trust model
# is that they are told and trusted. What per-student credentials buy is that
# every connection, channel and management action carries a name — which is the
# only thing standing between "someone did something odd" and an unanswerable
# question. See docs/plans/classroom-deployment.md.
set -euo pipefail

cd "$(dirname "$0")/.."

ROSTER="${1:-roster.csv}"
COMPOSE="docker compose -f server.compose.yml"

[[ -f .env ]] || { echo "No .env — copy .env.example and fill it in first." >&2; exit 1; }
[[ -f "$ROSTER" ]] || { echo "No roster at $ROSTER (start from roster.example)." >&2; exit 1; }
# shellcheck disable=SC1091
set -a; source .env; set +a
: "${CLTL_HOSTNAME:?set CLTL_HOSTNAME in .env}"
: "${CLTL_IMAGE_TAG:?set CLTL_IMAGE_TAG in .env}"

mkdir -p secrets/students sheets secrets/caddy
chmod 700 secrets sheets

# Caddy needs bcrypt hashes; the caddy image is the tool that makes them, and it
# is already on this host.
hash_password() { docker run --rm caddy:2.8-alpine caddy hash-password --plaintext "$1"; }
new_password()  { openssl rand -base64 24 | tr -d '/+=' | cut -c1-24; }

STUDENT_AUTH=secrets/caddy/students.auth
# Built beside the live file and moved into place only once every student has
# been handled, so a run that dies halfway leaves the credentials that are
# currently working exactly as they were.
trap 'rm -f "$STUDENT_AUTH.new"' EXIT
: > "$STUDENT_AUTH.new"

while IFS=, read -r student tenant broker_user; do
    # Skip comments and blank lines, so roster.example can be copied as-is.
    [[ -z "${student// }" || "${student#\#}" != "$student" ]] && continue
    student="${student// }"; tenant="${tenant// }"; broker_user="${broker_user// }"

    # The tenant id becomes one word of a routing key. A '.' would split it into
    # two, and '*' or '#' would turn a binding into a wildcard that quietly
    # reads everyone. custom-module enforces this at rung 4 and NOT at rungs
    # 1-2, which is where the students actually are — so it is enforced here.
    if [[ ! "$tenant" =~ ^[a-z0-9][a-z0-9_-]*$ ]]; then
        echo "roster: tenant id '$tenant' (student $student) must match ^[a-z0-9][a-z0-9_-]*$" >&2
        exit 1
    fi

    secret="secrets/students/$student.env"
    if [[ -f "$secret" ]]; then
        # shellcheck disable=SC1090
        source "$secret"
        echo "keeping existing credentials for $student"
    else
        BROKER_PASS="$(new_password)"
        STORAGE_PASS="$(new_password)"
        umask 077
        cat > "$secret" <<EOF
BROKER_PASS=$BROKER_PASS
STORAGE_PASS=$STORAGE_PASS
EOF
        echo "created credentials for $student"
    fi

    # Broker user. `|| true` on add: the user may already exist from a previous
    # run, and set_permissions below is the part that must always apply.
    $COMPOSE exec -T rabbitmq rabbitmqctl add_user "$broker_user" "$BROKER_PASS" >/dev/null 2>&1 || \
        $COMPOSE exec -T rabbitmq rabbitmqctl change_password "$broker_user" "$BROKER_PASS" >/dev/null
    # Permissive on purpose — see the header.
    $COMPOSE exec -T rabbitmq rabbitmqctl set_permissions -p / "$broker_user" '.*' '.*' '.*' >/dev/null
    # No tags: a student is not a monitor and certainly not an administrator,
    # so the management UI stays closed to them even though the broker is open.
    $COMPOSE exec -T rabbitmq rabbitmqctl set_user_tags "$broker_user" >/dev/null

    echo "$student $(hash_password "$STORAGE_PASS")" >> "$STUDENT_AUTH.new"

    umask 077
    cat > "sheets/$student.txt" <<EOF
ma-combot-2026 — connection sheet for $student
================================================================

These four values are yours. The two passwords are different from each other
and from anyone else's. Do not paste them into chat, issues or screenshots; ask
for a reissue instead, it takes a minute.

1. Your tenant id
   $tenant

   This goes in student/.env as CLTL_TENANT *and* in the notebook as TENANT.
   If the two disagree, nothing happens when you type — no error anywhere.

2. Your broker URL          (student/.env -> CLTL_AMQP_URL, notebook -> AMQP_URL)
   amqps://$broker_user:$BROKER_PASS@$CLTL_HOSTNAME:5671/?heartbeat=30

   Keep the ?heartbeat=30. Without it, closing your laptop lid leaves a queue
   bound on the server until TCP eventually notices.

3. Your storage URL         (student/.env -> CLTL_STORAGE_URL, notebook -> STORAGE_URL)
   https://$student:$STORAGE_PASS@$CLTL_HOSTNAME/storage/

   The trailing slash is load-bearing: the reference is resolved with urljoin(),
   which drops the last segment of a base that lacks one.

4. The image tag for this term
   $CLTL_IMAGE_TAG

Your chat UI, once you have started your own stack, is
   http://localhost:8000/chatui/static/chat.html
and it stays blank until your notebook opens a scenario. That is not a fault.

Start here: docs/student.md
EOF
done < "$ROSTER"

mv "$STUDENT_AUTH.new" "$STUDENT_AUTH"
chmod 600 "$STUDENT_AUTH"

# The instructor's own credential for the management UI, created once.
if [[ ! -f secrets/caddy/admin.auth ]]; then
    ADMIN_UI_PASS="$(new_password)"
    umask 077
    echo "admin $(hash_password "$ADMIN_UI_PASS")" > secrets/caddy/admin.auth
    echo "management UI: https://$CLTL_HOSTNAME/rabbitmq/  admin / $ADMIN_UI_PASS"
    echo "  (shown once — it is stored only as a bcrypt hash)"
fi

$COMPOSE restart caddy >/dev/null
echo
echo "Done. Connection sheets are in sheets/ — hand them out individually."

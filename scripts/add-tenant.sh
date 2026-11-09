#!/usr/bin/env bash
# Adds one tenant user to a server installed by scripts/install-server.sh,
# without re-running the installer:
#
#   scripts/add-tenant.sh tenant-c
#
# The user is named after the tenant id and confined to routing keys ending
# in it, exactly like the users created from a --tenants file. Its URL is
# appended to config/tenants.urls and printed. Run again for an existing id
# and it re-applies that user's password and permissions, unchanged.
set -euo pipefail

CLTL_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=scripts/common.sh
source "$CLTL_ROOT/scripts/common.sh"

[[ $# -eq 1 && $1 != -* ]] || { sed -n '2,11p' "$0" | sed 's/^# \{0,1\}//'; exit 2; }
id=$1

require_owner
validate_tenant_id "$id"
hostname=$(kv_get "$CLTL_ENV_FILE" CLTL_HOSTNAME)
[[ -n $hostname ]] || die "no CLTL_HOSTNAME in $CLTL_ENV_FILE; run scripts/install-server.sh first"
compose exec -T rabbitmq true < /dev/null 2> /dev/null || die "the event bus is not running (systemctl status cltl-server)"

reconcile_tenants "$hostname" "$id"
log "Tenant $id:"
awk -v id="$id" '$1 == id { print $2 }' "$CLTL_TENANTS_URLS"

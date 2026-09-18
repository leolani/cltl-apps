#!/usr/bin/env bash
# Replace one student's credentials and write them a fresh connection sheet.
#
#   bin/reissue.sh alice roster.csv
#
# For the ordinary case: someone pasted their sheet into a group chat, or lost
# it. Reissuing is a minute's work and is always the right answer — a shared
# credential is the one thing this deployment's trust model cannot absorb,
# because it is attribution, not isolation, that holds everything together here.
set -euo pipefail

cd "$(dirname "$0")/.."

STUDENT="${1:?usage: bin/reissue.sh <student> [roster.csv]}"
ROSTER="${2:-roster.csv}"

[[ -f "secrets/students/$STUDENT.env" ]] || {
    echo "No existing credentials for '$STUDENT' — is the name right?" >&2
    echo "Known:" >&2
    find secrets/students -name '*.env' -exec basename {} .env \; 2>/dev/null | sed 's/^/  /' >&2
    exit 1
}

rm -f "secrets/students/$STUDENT.env"
echo "Dropped $STUDENT's stored credentials; regenerating."

# provision.sh keeps existing credentials and creates missing ones, so removing
# the file above is the whole of the reissue. Everyone else is untouched.
exec bin/provision.sh "$ROSTER"

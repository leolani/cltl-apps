#!/usr/bin/env bash
# Delete uploaded images older than a retention window.
#
#   bin/prune-images.sh [days]        # default 30
#
# This exists because nothing else will do it. `CachedImageStorage` has no
# delete path at all — `store` writes a PNG and a `_meta.json` per upload and
# there is no code anywhere in cltl-backend that removes either. On a laptop for
# an afternoon that is invisible. Over a term, with a class uploading pictures,
# it is the thing that fills the disk.
#
# And a full disk here is not a storage problem, it is an everyone problem:
# RabbitMQ's data lives on the same filesystem, crossing disk_free_limit raises
# an alarm, and an alarmed broker BLOCKS PUBLISHERS. Every student's chat UI
# stops working at once, with nothing in any log that points at a photograph
# from three weeks ago.
#
# Deleting pixels does not break a past conversation in any way a student will
# see: the transcript keeps its own copy of the image it echoed, and the
# `cltl-storage:` reference only matters while something is still fetching it.
set -euo pipefail

cd "$(dirname "$0")/.."

DAYS="${1:-30}"
DIR="storage/image"

[[ -d "$DIR" ]] || { echo "No $DIR here — run this from a checkout with the server in it." >&2; exit 1; }

before=$(du -sh "$DIR" 2>/dev/null | cut -f1)
count=$(find "$DIR" -type f ! -name '.gitkeep' -mtime "+$DAYS" -print | wc -l)

find "$DIR" -type f ! -name '.gitkeep' -mtime "+$DAYS" -delete

after=$(du -sh "$DIR" 2>/dev/null | cut -f1)
echo "Pruned $count file(s) older than $DAYS days from $DIR ($before -> $after)."

# Worth seeing next to the result: the number that matters is the one in
# config/rabbitmq.conf, and it is the broker that enforces it.
df -h . | awk 'NR==1 || NR==2 {print "  " $0}'

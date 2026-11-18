#!/bin/sh
# SHEM backend container entrypoint.
#
# With LITESTREAM_BUCKET set: restore the SQLite database from the replica
# (only when there is no local file yet, i.e. after a restart/redeploy on an
# ephemeral disk), then run the app under `litestream replicate`, which streams
# every change to object storage and does a final sync on shutdown.
# Without it: run the app directly (local SQLite or Turso, as configured).
set -e

export SQLITE_PATH="${SQLITE_PATH:-/app/data/shem.db}"
export LITESTREAM_PATH="${LITESTREAM_PATH:-shem.db}"
mkdir -p "$(dirname "$SQLITE_PATH")"

if [ -n "$LITESTREAM_BUCKET" ]; then
  if [ -n "$TURSO_DATABASE_URL" ] || [ -n "$DATABASE_URL" ]; then
    echo "litestream: TURSO_DATABASE_URL/DATABASE_URL is set, so the app would not use the SQLite file." >&2
    echo "litestream: remove those variables to use SQLite + Litestream." >&2
    exit 1
  fi
  echo "litestream: restoring $SQLITE_PATH from s3://$LITESTREAM_BUCKET/$LITESTREAM_PATH (if a replica exists)"
  litestream restore -config /app/litestream.yml -if-db-not-exists -if-replica-exists "$SQLITE_PATH"
  echo "litestream: replicating; starting SHEM backend"
  exec litestream replicate -config /app/litestream.yml -exec "python run.py"
fi

echo "LITESTREAM_BUCKET not set: starting without replication (data on this disk only)"
exec python run.py

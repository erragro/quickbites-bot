#!/usr/bin/env bash
# Cloud Run entrypoint: starts an embedded Postgres on /tmp, waits ready,
# then execs uvicorn. The DB is ephemeral (re-bootstrapped from app.db on
# every cold start) which is fine for this workload — bot lookup data is
# read-only and sessions are short-lived per eval run.
set -euo pipefail

PGUSER=quickbites
PGPASSWORD=quickbites
PGDB=quickbites
export PGDATA=/tmp/pgdata

PG_BIN="$(ls -d /usr/lib/postgresql/*/bin | head -n 1)"
echo "[entrypoint] using $PG_BIN"

mkdir -p "$PGDATA" /tmp/pg-run
chown -R postgres:postgres "$PGDATA" /tmp/pg-run

if [ ! -s "$PGDATA/PG_VERSION" ]; then
  echo "[entrypoint] initdb"
  su postgres -c "$PG_BIN/initdb -D $PGDATA -U postgres --auth-local=trust --auth-host=trust >/dev/null"
fi

echo "[entrypoint] starting postgres"
su postgres -c "$PG_BIN/pg_ctl -D $PGDATA -l /tmp/pg.log \
  -o '-c listen_addresses=127.0.0.1 -c port=5432 -c unix_socket_directories=/tmp/pg-run -c shared_buffers=64MB -c max_connections=20' \
  -w start"

for i in $(seq 1 30); do
  if su postgres -c "$PG_BIN/pg_isready -h 127.0.0.1 -p 5432 -U postgres" >/dev/null 2>&1; then
    break
  fi
  sleep 0.3
done

su postgres -c "psql -h 127.0.0.1 -U postgres -tc \"SELECT 1 FROM pg_roles WHERE rolname='$PGUSER'\"" \
  | grep -q 1 \
  || su postgres -c "psql -h 127.0.0.1 -U postgres -c \"CREATE ROLE $PGUSER WITH LOGIN PASSWORD '$PGPASSWORD' SUPERUSER\""
su postgres -c "psql -h 127.0.0.1 -U postgres -tc \"SELECT 1 FROM pg_database WHERE datname='$PGDB'\"" \
  | grep -q 1 \
  || su postgres -c "psql -h 127.0.0.1 -U postgres -c \"CREATE DATABASE $PGDB OWNER $PGUSER\""

export DATABASE_URL="postgresql+psycopg://${PGUSER}:${PGPASSWORD}@127.0.0.1:5432/${PGDB}"
echo "[entrypoint] launching uvicorn on :${PORT:-8080}"
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8080}"

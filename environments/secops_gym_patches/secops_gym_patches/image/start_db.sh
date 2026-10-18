#!/bin/sh
# Start the task's Postgres (port 5433) if it is not already running. Idempotent.
set -e
mkdir -p /run/postgresql && chown postgres:postgres /run/postgresql
if ! su postgres -s /bin/sh -c "pg_ctl -D /var/lib/gympg status" >/dev/null 2>&1; then
    su postgres -s /bin/sh -c "pg_ctl -D /var/lib/gympg -l /var/lib/gympg/server.log -w start" >/dev/null
fi

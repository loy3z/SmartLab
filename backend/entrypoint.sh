#!/bin/sh
# Sprint 3 (2026-10-25): wait for PostgreSQL, create the schema on the first start, apply every
# migration (they are safe to run again), then serve with gunicorn.
set -e

export PGPASSWORD="${DB_PASSWORD}"

echo "Waiting for PostgreSQL at ${DB_HOST}:${DB_PORT} ..."
until pg_isready -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" >/dev/null 2>&1; do
  sleep 2
done
echo "PostgreSQL is ready."

PSQL="psql -h ${DB_HOST} -p ${DB_PORT} -U ${DB_USER} -d ${DB_NAME} -v ON_ERROR_STOP=1"

# First start: the dump creates every table. schema.sql ends with pg_dump 18 meta commands
# (\restrict / \unrestrict) that older psql clients do not know, so strip those two lines.
if [ "$($PSQL -tAc "SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='app_users'")" != "1" ]; then
  echo "Creating the database schema ..."
  grep -v '^\\restrict' database/schema.sql | grep -v '^\\unrestrict' > /tmp/schema.sql
  $PSQL -q -f /tmp/schema.sql
fi

for file in database/migrations/*.sql; do
  echo "Applying ${file} ..."
  $PSQL -q -f "${file}"
done

exec gunicorn config.wsgi:application \
  --bind 0.0.0.0:8000 \
  --workers "${GUNICORN_WORKERS:-3}" \
  --timeout 120 \
  --access-logfile -

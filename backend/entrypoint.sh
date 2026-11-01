#!/bin/sh
# Sprint 3 (2026-10-25): wait for PostgreSQL, create the schema (and, for a demo, the demo data) when the
# database is new, then serve with gunicorn.
#
# Migrations are NOT run on every start (review 2026-10-25): schema.sql is already the latest structure, and
# migration 005 resets the demo staff passwords, so re-running it would undo password changes. When a later
# release adds a migration, apply it once with the new image before switching containers (DEPLOY.md section 3):
#   docker compose --env-file .env.docker build
#   docker compose --env-file .env.docker run --rm api migrate database/migrations/009_example.sql
#   docker compose --env-file .env.docker up -d
set -e

export PGPASSWORD="${DB_PASSWORD}"
PSQL="psql -h ${DB_HOST} -p ${DB_PORT} -U ${DB_USER} -d ${DB_NAME} -v ON_ERROR_STOP=1 -q"

# The dumps end with pg_dump 18 meta commands (\restrict / \unrestrict) that older psql clients do not
# know; drop those lines. All files given run in one transaction: either all of them apply or none.
run_sql() {
  : > /tmp/run.sql
  for file in "$@"; do
    grep -v -e '^\\restrict' -e '^\\unrestrict' "${file}" >> /tmp/run.sql
  done
  $PSQL --single-transaction -o /dev/null -f /tmp/run.sql
}

echo "Waiting for PostgreSQL at ${DB_HOST}:${DB_PORT} ..."
until pg_isready -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" >/dev/null 2>&1; do
  sleep 2
done

if [ "$1" = "migrate" ]; then
  shift
  [ "$#" -gt 0 ] || { echo "Usage: ./entrypoint.sh migrate database/migrations/<file>.sql ..."; exit 2; }
  for file in "$@"; do
    echo "Applying ${file} ..."
    run_sql "${file}"
  done
  exit 0
fi

if [ "$($PSQL -tAc "SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='app_users'")" != "1" ]; then
  if [ "${LOAD_DEMO_DATA:-false}" = "true" ]; then
    echo "New database: creating the schema and loading the demo data (database/seed_*.sql) ..."
    run_sql database/schema.sql database/seed_resources.sql database/seed_users.sql
  else
    echo "New database: creating the schema ..."
    run_sql database/schema.sql
  fi
fi

# Run a Django management command after the database is ready. The scheduler service uses this
# path so it shares the same image and database configuration as the API service.
if [ "$1" = "manage" ]; then
  shift
  [ "$#" -gt 0 ] || { echo "Usage: ./entrypoint.sh manage <command> [arguments...]"; exit 2; }
  exec python manage.py "$@"
fi

exec gunicorn config.wsgi:application \
  --bind 0.0.0.0:8000 \
  --workers "${GUNICORN_WORKERS:-3}" \
  --timeout 120 \
  --access-logfile -

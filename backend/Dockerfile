# Sprint 3 (2026-10-25): production image for the API (gunicorn + PostgreSQL).
# Built by docker-compose.yml; entrypoint.sh creates the schema on a new database (steps: DEPLOY.md).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# psql creates the schema and applies migrations; curl is used by the container health check.
RUN apt-get update \
    && apt-get install -y --no-install-recommends postgresql-client curl \
    && rm -rf /var/lib/apt/lists/*

# The same locked versions as the local PostgreSQL setup (requirements-postgres.txt includes the lock file).
COPY requirements-lock.txt requirements-postgres.txt ./
RUN pip install --no-cache-dir -r requirements-postgres.txt gunicorn==23.0.0

COPY . .
# The repository keeps CRLF for Windows; a shell script inside Linux must be LF-only.
RUN sed -i 's/\r$//' entrypoint.sh && chmod +x entrypoint.sh

EXPOSE 8000
ENTRYPOINT ["./entrypoint.sh"]

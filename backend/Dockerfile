# Sprint 3 (2026-10-25): production image for the API (gunicorn + PostgreSQL).
# Built by docker-compose.yml; the SQL migrations run from entrypoint.sh on start.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# psql runs the SQL migrations at startup; curl is used by the container health check.
RUN apt-get update \
    && apt-get install -y --no-install-recommends postgresql-client curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn "psycopg[binary]"

COPY . .
# The repository keeps CRLF for Windows; a shell script inside Linux must be LF-only.
RUN sed -i 's/\r$//' entrypoint.sh && chmod +x entrypoint.sh

EXPOSE 8000
ENTRYPOINT ["./entrypoint.sh"]

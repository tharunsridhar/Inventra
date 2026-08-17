#!/bin/sh
# Runs before the CMD on every container start (see Dockerfile ENTRYPOINT).
# docker-compose's `depends_on: postgres: condition: service_healthy`
# guarantees Postgres is already accepting connections by the time this
# runs, so there's no wait-for-it loop here - just migrate, then hand off.
set -e

echo "Running database migrations..."
alembic upgrade head

echo "Starting application..."
exec "$@"

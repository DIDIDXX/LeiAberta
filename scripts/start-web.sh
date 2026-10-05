#!/bin/sh
set -eu

attempt=0
until alembic upgrade head; do
  attempt=$((attempt + 1))
  if [ "$attempt" -ge 20 ]; then
    echo "Database migration did not succeed after 20 attempts" >&2
    exit 1
  fi
  echo "Retrying PostgreSQL migration after a reported error (attempt $attempt/20)" >&2
  sleep 1
done
echo "Database migrations are at the current Alembic head" >&2

python -m app.seed --enqueue-hot
# Catalog refreshes and maintenance audits stay off the HTTP startup path; the
# worker refreshes jurisdiction and legislative catalogs asynchronously.
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"

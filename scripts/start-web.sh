#!/bin/sh
set -eu

attempt=0
until alembic upgrade head; do
  attempt=$((attempt + 1))
  if [ "$attempt" -ge 20 ]; then
    echo "Database migration did not succeed after 20 attempts" >&2
    exit 1
  fi
  echo "Waiting for PostgreSQL before migration (attempt $attempt/20)" >&2
  sleep 3
done

python -m app.seed --enqueue-hot
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"

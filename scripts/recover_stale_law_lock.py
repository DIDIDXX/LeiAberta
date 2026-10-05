"""Reclaim only the verified, stale production laws-table lock from 2026-10-05."""
from __future__ import annotations

import os
import sys

from sqlalchemy import create_engine, text

from app.db import normalize_database_url


# This identity came from pg_stat_activity after repeated migration failures.
# Every field is matched so a future process reusing this PID is left alone.
STALE_BACKEND = {
    "pid": 11882,
    "client_address": "fd12:7e41:f1ed:1:3000:da:da17:e997",
    "client_port": 38720,
    "backend_start": "2026-10-05 04:03:57.372617+00:00",
    "query_start": "2026-10-05 04:04:03.826390+00:00",
    "state_change": "2026-10-05 04:04:03.826407+00:00",
    "xact_start": "2026-10-05 04:04:02.859806+00:00",
}

MATCH_STALE_BACKEND = text("""
    SELECT a.pid
    FROM pg_stat_activity AS a
    JOIN pg_locks AS l ON l.pid = a.pid
    JOIN pg_class AS c ON c.oid = l.relation
    JOIN pg_namespace AS n ON n.oid = c.relnamespace
    WHERE a.pid = :pid
      AND a.usename = current_user
      AND a.backend_type = 'client backend'
      AND a.client_addr = CAST(:client_address AS inet)
      AND a.client_port = :client_port
      AND a.backend_start = CAST(:backend_start AS timestamptz)
      AND a.query_start = CAST(:query_start AS timestamptz)
      AND a.state_change = CAST(:state_change AS timestamptz)
      AND a.xact_start = CAST(:xact_start AS timestamptz)
      AND a.state = 'active'
      AND a.wait_event_type = 'Client'
      AND a.wait_event = 'ClientRead'
      AND n.nspname = 'public'
      AND c.relname = 'laws'
      AND l.mode = 'RowShareLock'
      AND l.granted
      AND a.pid <> pg_backend_pid()
    LIMIT 1
""")


def main() -> None:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL is required for stale-lock recovery")

    engine = create_engine(normalize_database_url(database_url), pool_pre_ping=True)
    try:
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            pid = connection.execute(MATCH_STALE_BACKEND, STALE_BACKEND).scalar_one_or_none()
            if pid is None:
                print("No exact match for the previously identified stale laws-table lock")
                return

            terminated = connection.execute(
                text("SELECT pg_terminate_backend(:pid)"),
                {"pid": pid},
            ).scalar_one()
            if not terminated:
                print(f"Could not terminate verified stale PostgreSQL backend pid={pid}", file=sys.stderr)
                raise SystemExit(1)

            print(f"Terminated verified stale laws-table lock backend pid={pid}")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()

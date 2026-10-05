"""Reclaim only the verified, stale production laws-table locks from 2026-10-05."""
from __future__ import annotations

import os
import sys

from sqlalchemy import create_engine, text


# These identities came from pg_stat_activity after repeated migration failures.
# Match every field so a future process reusing any PID is left alone.
STALE_BACKENDS = (
    {
        "pid": 11882,
        "client_address": "fd12:7e41:f1ed:1:3000:da:da17:e997",
        "client_port": 38720,
        "backend_start": "2026-10-05 04:03:57.372617+00:00",
        "query_start": "2026-10-05 04:04:03.826390+00:00",
        "state_change": "2026-10-05 04:04:03.826407+00:00",
        "xact_start": "2026-10-05 04:04:02.859806+00:00",
        "lock_mode": "RowShareLock",
    },
    {
        "pid": 15737,
        "client_address": "fd12:7e41:f1ed:1:3000:aa:cb96:a46a",
        "client_port": 36692,
        "backend_start": "2026-10-05 07:02:08.047261+00:00",
        "query_start": "2026-10-05 07:05:09.274436+00:00",
        "state_change": "2026-10-05 07:05:09.274437+00:00",
        "xact_start": "2026-10-05 07:05:08.096592+00:00",
        "lock_mode": "RowExclusiveLock",
    },
    {
        "pid": 17037,
        "client_address": "fd12:7e41:f1ed:1:3000:c4:e6de:3f1d",
        "client_port": 33758,
        "backend_start": "2026-10-05 07:27:10.509645+00:00",
        "query_start": "2026-10-05 07:31:11.371661+00:00",
        "state_change": "2026-10-05 07:31:11.371661+00:00",
        "xact_start": "2026-10-05 07:31:09.904427+00:00",
        "lock_mode": "RowExclusiveLock",
    },
)


def normalize_database_url(value: str) -> str:
    if value.startswith("postgres://"):
        return value.replace("postgres://", "postgresql+psycopg://", 1)
    if value.startswith("postgresql://"):
        return value.replace("postgresql://", "postgresql+psycopg://", 1)
    return value


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
      AND l.mode = :lock_mode
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
            matched = 0
            for stale_backend in STALE_BACKENDS:
                pid = connection.execute(MATCH_STALE_BACKEND, stale_backend).scalar_one_or_none()
                if pid is None:
                    continue
                matched += 1
                terminated = connection.execute(
                    text("SELECT pg_terminate_backend(:pid)"),
                    {"pid": pid},
                ).scalar_one()
                if not terminated:
                    print(f"Could not terminate verified stale PostgreSQL backend pid={pid}", file=sys.stderr)
                    raise SystemExit(1)
                print(f"Terminated verified stale laws-table lock backend pid={pid}")
            if matched == 0:
                print("No exact match for the previously identified stale laws-table locks")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()

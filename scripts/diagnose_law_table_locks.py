"""Log non-sensitive PostgreSQL lock metadata for the laws table."""
from __future__ import annotations

import json
import os

from sqlalchemy import create_engine, text


def main() -> None:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL is required for lock diagnostics")
    engine = create_engine(database_url, pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            rows = connection.execute(text("""
                SELECT a.pid, a.application_name, a.backend_type, a.state,
                       a.wait_event_type, a.wait_event,
                       EXTRACT(EPOCH FROM now() - a.xact_start)::integer AS transaction_age_seconds,
                       array_agg(DISTINCT l.mode ORDER BY l.mode) AS held_lock_modes
                FROM pg_locks AS l
                JOIN pg_class AS c ON c.oid = l.relation
                JOIN pg_namespace AS n ON n.oid = c.relnamespace
                JOIN pg_stat_activity AS a ON a.pid = l.pid
                WHERE n.nspname = 'public' AND c.relname = 'laws'
                  AND l.granted AND a.pid <> pg_backend_pid()
                GROUP BY a.pid, a.application_name, a.backend_type, a.state,
                         a.wait_event_type, a.wait_event, a.xact_start
                ORDER BY a.xact_start NULLS LAST
                LIMIT 30
            """)).mappings().all()
        print("law_table_lock_holders=" + json.dumps([dict(row) for row in rows], default=str), flush=True)
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()

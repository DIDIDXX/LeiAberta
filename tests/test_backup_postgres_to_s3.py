import json
from types import SimpleNamespace

from scripts import backup_postgres_to_s3 as backup


def test_db_metadata_includes_relation_sizes_and_job_outbox_counts(monkeypatch):
    metadata = {
        "server_version": "18.0",
        "server_version_num": "180000",
        "database_size_bytes": 123456,
        "row_counts": {"source_snapshots": 12, "hydration_jobs": 9, "job_outbox": 8},
        "relation_sizes": [{
            "schema": "public", "table": "source_snapshots", "total_bytes": 5000,
            "heap_bytes": 4000, "index_bytes": 1000,
            "live_rows_estimate": 12, "dead_rows_estimate": 1,
        }],
        "job_status_counts": {"queued": 3, "succeeded": 6},
        "job_type_status_counts": [{"job_type": "hydrate", "status": "queued", "count": 3}],
        "outbox_dispatch_state_counts": {"pending": 2, "dispatched": 6},
        "alembic_versions": ["20261005_0010"],
    }
    calls = []

    def fake_run(args, *, timeout, database_url=None):
        calls.append((args, timeout, database_url))
        return SimpleNamespace(stdout=json.dumps(metadata), returncode=0)

    monkeypatch.setattr(backup, "_run_postgres", fake_run)

    result = backup._db_metadata("postgresql+psycopg://example.invalid/app")

    assert result == metadata
    assert len(calls) == 1
    args, timeout, database_url = calls[0]
    assert args[0] == "psql"
    assert timeout == 180
    assert database_url == "postgresql+psycopg://example.invalid/app"
    assert "pg_total_relation_size(relid)" in args[-1]
    assert "pg_relation_size(relid)" in args[-1]
    assert "pg_indexes_size(relid)" in args[-1]
    assert "n_live_tup" in args[-1] and "n_dead_tup" in args[-1]
    assert "GROUP BY status" in args[-1]
    assert "GROUP BY job_type, status" in args[-1]
    assert "GROUP BY dispatch_state" in args[-1]
    assert "raw_body" not in args[-1]
    assert "SELECT *" not in args[-1].upper()

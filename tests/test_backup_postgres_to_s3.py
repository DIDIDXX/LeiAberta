import hashlib
import io
import json
from types import SimpleNamespace

import pytest

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
        "schema_inventory": {
            "columns": [{"table": "laws", "column": "id", "ordinal": 1, "data_type": "uuid"}],
            "constraints": [{"table": "laws", "name": "laws_pkey", "type": "p", "validated": True,
                             "definition": "PRIMARY KEY (id)"}],
            "indexes": [{"table": "laws", "name": "laws_pkey", "definition": "CREATE UNIQUE INDEX laws_pkey"}],
            "triggers": [], "extensions": [{"name": "plpgsql", "version": "1.0"}],
        },
    }
    calls = []

    def fake_run(args, *, timeout, database_url=None):
        calls.append((args, timeout, database_url))
        return SimpleNamespace(stdout=json.dumps(metadata), returncode=0)

    monkeypatch.setattr(backup, "_run_postgres", fake_run)

    result = backup._db_metadata("postgresql+psycopg://example.invalid/app")

    assert {key: value for key, value in result.items() if key != "schema_signature"} == metadata
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
    assert "schema_inventory" in args[-1]
    assert "pg_get_constraintdef" in args[-1]
    assert "pg_get_triggerdef" in args[-1]
    assert "FROM pg_sequences WHERE schemaname = 'public'" in args[-1]
    assert "FROM pg_views WHERE schemaname = 'public'" in args[-1]
    assert "raw_body" not in args[-1]
    assert "SELECT *" not in args[-1].upper()
    assert result["schema_signature"] == backup._schema_signature(metadata["schema_inventory"])


def test_schema_signature_is_stable_for_object_key_order():
    first = {"columns": [{"table": "laws", "column": "id"}], "extensions": []}
    second = {"extensions": [], "columns": [{"column": "id", "table": "laws"}]}
    assert backup._schema_signature(first) == backup._schema_signature(second)


def test_restore_validation_requires_counts_revision_and_schema_match():
    expected = {"row_counts": {"laws": 3}, "alembic_versions": ["head"], "schema_signature": "sig"}
    backup._validate_restore_metadata(expected, expected)

    for key, value, message in (
        ("row_counts", {"laws": 2}, "row counts differ"),
        ("alembic_versions", ["older"], "migration versions differ"),
        ("schema_signature", "different", "schema signature differs"),
    ):
        restored = {**expected, key: value}
        with pytest.raises(RuntimeError, match=message):
            backup._validate_restore_metadata(restored, expected)


def test_uploaded_dump_is_read_back_and_hashed():
    data = b"verified custom-format dump"
    checksum = hashlib.sha256(data).hexdigest()

    class FakeS3:
        def head_object(self, **kwargs):
            return {"ContentLength": len(data), "Metadata": {"sha256": checksum}}

        def get_object(self, **kwargs):
            return {"Body": io.BytesIO(data)}

    assert backup._verify_uploaded_dump(FakeS3(), "bucket", "backup.dump", len(data), checksum) == {
        "size_bytes": len(data), "sha256": checksum,
    }


@pytest.mark.parametrize("remote_data,content_length", [(b"X" * 27, 27), (b"short", 27)])
def test_uploaded_dump_mismatch_fails(remote_data, content_length):
    expected = b"verified custom-format dump"

    class FakeS3:
        def head_object(self, **kwargs):
            return {"ContentLength": content_length, "Metadata": {}}

        def get_object(self, **kwargs):
            return {"Body": io.BytesIO(remote_data)}

    with pytest.raises(RuntimeError, match="size mismatch|byte verification failed"):
        backup._verify_uploaded_dump(
            FakeS3(), "bucket", "backup.dump", len(expected), hashlib.sha256(expected).hexdigest()
        )


def test_uploaded_manifest_readback_is_exact():
    manifest = b'{"dump_key":"one.dump","sha256":"abc"}'

    class FakeS3:
        def get_object(self, **kwargs):
            return {"Body": io.BytesIO(manifest)}

    assert backup._verify_uploaded_manifest(FakeS3(), "bucket", "one.dump.json", manifest) == hashlib.sha256(
        manifest
    ).hexdigest()

    class CorruptS3:
        def get_object(self, **kwargs):
            return {"Body": io.BytesIO(manifest + b"x")}

    with pytest.raises(RuntimeError, match="manifest read-back mismatch"):
        backup._verify_uploaded_manifest(CorruptS3(), "bucket", "one.dump.json", manifest)


@pytest.mark.parametrize("verify_restore,should_apply_retention", [("0", False), ("1", True)])
def test_backup_gates_destructive_retention_on_restore_verification(
    monkeypatch, verify_restore, should_apply_retention
):
    source = {
        "server_version": "18.0", "server_version_num": "180000", "database_size_bytes": 1,
        "row_counts": {"laws": 1}, "alembic_versions": ["head"], "schema_inventory": {},
        "schema_signature": backup._schema_signature({}),
    }

    class FakeS3:
        def __init__(self):
            self.objects = {}

        def upload_file(self, path, bucket, key, ExtraArgs):
            self.objects[key] = {"data": open(path, "rb").read(), "metadata": ExtraArgs["Metadata"]}

        def head_object(self, Bucket, Key):
            item = self.objects[Key]
            return {"ContentLength": len(item["data"]), "Metadata": item["metadata"]}

        def get_object(self, Bucket, Key):
            return {"Body": io.BytesIO(self.objects[Key]["data"])}

        def put_object(self, Bucket, Key, Body, ContentType):
            self.objects[Key] = {"data": Body, "metadata": {}}

    client = FakeS3()
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://user:secret@example.invalid/db")
    monkeypatch.setenv("BACKUP_S3_BUCKET", "test-bucket")
    monkeypatch.setenv("BACKUP_VERIFY_RESTORE", verify_restore)
    monkeypatch.setattr(backup, "_db_metadata", lambda _url: source)
    monkeypatch.setattr(backup, "_verify_restore", lambda _path, _expected: source)
    monkeypatch.setattr(backup, "_s3_client", lambda: client)
    retention_calls = []
    monkeypatch.setattr(backup, "_apply_retention", lambda *args: retention_calls.append(args) or 0)

    def fake_run(args, *, timeout, database_url=None):
        if args[0] == "pg_dump":
            Path_arg = args[args.index("--file") + 1]
            with open(Path_arg, "wb") as target:
                target.write(b"test dump")
        return SimpleNamespace(stdout="", returncode=0)

    monkeypatch.setattr(backup, "_run_postgres", fake_run)
    result = backup.run_backup()

    assert result["uploaded_object_verified"] is True
    assert result["restore_verified"] is should_apply_retention
    assert result["manifest_sha256"]
    assert bool(retention_calls) is should_apply_retention
    uploaded_manifest = next(value["data"] for key, value in client.objects.items() if key.endswith(".dump.json"))
    stored_manifest = json.loads(uploaded_manifest)
    assert stored_manifest["uploaded_object_verified"] is True
    assert stored_manifest["sha256"] == stored_manifest["uploaded_object_sha256"]

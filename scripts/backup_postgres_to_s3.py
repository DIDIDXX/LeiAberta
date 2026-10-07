"""Create and validate a PostgreSQL dump, then retain it in Railway Object Storage."""
from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import socket
import subprocess
import tempfile
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(message)s")
logger = logging.getLogger("leiaberta.backup")
ROW_COUNT_TABLES = (
    "laws", "law_versions", "legal_nodes", "law_changes", "history_events",
    "senate_proceedings", "source_snapshots", "source_registry", "hydration_jobs", "job_outbox",
)


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Required backup configuration is missing: {name}")
    return value


def _libpq_url(database_url: str) -> str:
    # SQLAlchemy's driver-qualified scheme is not accepted by pg_dump/psql.
    return database_url.replace("postgresql+psycopg://", "postgresql://", 1)


def _run_postgres(args: list[str], *, timeout: int, database_url: str | None = None) -> subprocess.CompletedProcess:
    def redact(detail: str) -> str:
        if database_url:
            detail = detail.replace(database_url, "[DATABASE_URL]")
            detail = detail.replace(_libpq_url(database_url), "[DATABASE_URL]")
        return detail

    try:
        result = subprocess.run(args, check=False, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        detail = exc.stderr or exc.stdout or ""
        if isinstance(detail, bytes):
            detail = detail.decode("utf-8", errors="replace")
        detail = str(detail).strip()
        detail = redact(detail)
        suffix = f": {detail[:1000]}" if detail else ""
        raise RuntimeError(f"{Path(args[0]).name} timed out after {timeout} seconds{suffix}") from None
    if result.returncode:
        detail = result.stderr.strip()
        detail = redact(detail)
        raise RuntimeError(f"{Path(args[0]).name} failed with exit code {result.returncode}: {detail[:1000]}")
    return result


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _db_metadata(database_url: str) -> dict:
    row_counts = ",".join(
        f"'{table}', (SELECT COUNT(*) FROM public.{table})" for table in ROW_COUNT_TABLES
    )
    query = (
        "SELECT json_build_object("
        "'server_version', current_setting('server_version'), "
        "'server_version_num', current_setting('server_version_num'), "
        "'database_size_bytes', pg_database_size(current_database()), "
        f"'row_counts', json_build_object({row_counts}), "
        "'legal_content_checks', json_build_object("
        "'civil_code_exists', EXISTS(SELECT 1 FROM public.laws WHERE slug = '10406-2002'), "
        "'art389_node_exists', EXISTS(SELECT 1 FROM public.laws l "
        "JOIN public.legal_nodes n ON n.version_id = l.current_version_id "
        "WHERE l.slug = '10406-2002' AND n.node_id = 'art:389'), "
        "'art389_text_md5', COALESCE((SELECT md5(n.text) FROM public.laws l "
        "JOIN public.legal_nodes n ON n.version_id = l.current_version_id "
        "WHERE l.slug = '10406-2002' AND n.node_id = 'art:389' LIMIT 1), ''), "
        "'art389_change_exists', EXISTS(SELECT 1 FROM public.law_changes "
        "WHERE id = 'be3a1531-edaa-5a78-94ca-70c6544e3853' "
        "AND law_slug = '10406-2002' AND node_id = 'art:389')"
        "), "
        "'relation_sizes', COALESCE(("
        "SELECT json_agg(json_build_object("
        "'schema', schemaname, 'table', relname, "
        "'total_bytes', pg_total_relation_size(relid), "
        "'heap_bytes', pg_relation_size(relid), 'index_bytes', pg_indexes_size(relid), "
        "'live_rows_estimate', n_live_tup, 'dead_rows_estimate', n_dead_tup"
        ") ORDER BY pg_total_relation_size(relid) DESC) FROM pg_stat_user_tables"
        "), '[]'::json), "
        "'job_status_counts', COALESCE(("
        "SELECT json_object_agg(status, row_count) FROM ("
        "SELECT status, count(*) AS row_count FROM public.hydration_jobs GROUP BY status"
        ") AS grouped_jobs"
        "), '{}'::json), "
        "'job_type_status_counts', COALESCE(("
        "SELECT json_agg(json_build_object('job_type', job_type, 'status', status, 'count', row_count) "
        "ORDER BY job_type, status) FROM ("
        "SELECT job_type, status, count(*) AS row_count FROM public.hydration_jobs GROUP BY job_type, status"
        ") AS grouped_job_types"
        "), '[]'::json), "
        "'outbox_dispatch_state_counts', COALESCE(("
        "SELECT json_object_agg(dispatch_state, row_count) FROM ("
        "SELECT CASE WHEN dispatched_at IS NULL THEN 'pending' ELSE 'dispatched' END AS dispatch_state, "
        "count(*) AS row_count FROM public.job_outbox GROUP BY dispatch_state"
        ") AS grouped_outbox"
        "), '{}'::json), "
        "'alembic_versions', COALESCE((SELECT json_agg(version_num ORDER BY version_num) "
        "FROM public.alembic_version), '[]'::json), "
        "'schema_inventory', json_build_object("
        "'columns', COALESCE((SELECT json_agg(json_build_object("
        "'table', table_name, 'column', column_name, 'ordinal', ordinal_position, "
        "'data_type', data_type, 'udt_name', udt_name, 'nullable', is_nullable, "
        "'default', column_default, 'identity', is_identity, "
        "'generation', generation_expression) ORDER BY table_name, ordinal_position) "
        "FROM information_schema.columns WHERE table_schema = 'public'), '[]'::json), "
        "'constraints', COALESCE((SELECT json_agg(json_build_object("
        "'table', rel.relname, 'name', con.conname, 'type', con.contype, "
        "'validated', con.convalidated, 'definition', pg_get_constraintdef(con.oid, true)) "
        "ORDER BY rel.relname, con.conname) FROM pg_constraint con "
        "JOIN pg_class rel ON rel.oid = con.conrelid "
        "JOIN pg_namespace ns ON ns.oid = rel.relnamespace "
        "WHERE ns.nspname = 'public'), '[]'::json), "
        "'indexes', COALESCE((SELECT json_agg(json_build_object("
        "'table', tablename, 'name', indexname, 'definition', indexdef) "
        "ORDER BY tablename, indexname) FROM pg_indexes WHERE schemaname = 'public'), '[]'::json), "
        "'triggers', COALESCE((SELECT json_agg(json_build_object("
        "'table', rel.relname, 'name', trg.tgname, 'definition', pg_get_triggerdef(trg.oid, true)) "
        "ORDER BY rel.relname, trg.tgname) FROM pg_trigger trg "
        "JOIN pg_class rel ON rel.oid = trg.tgrelid "
        "JOIN pg_namespace ns ON ns.oid = rel.relnamespace "
        "WHERE ns.nspname = 'public' AND NOT trg.tgisinternal), '[]'::json), "
        "'sequences', COALESCE((SELECT json_agg(json_build_object("
        "'name', sequencename, 'data_type', data_type, 'start', start_value, "
        "'minimum', min_value, 'maximum', max_value, 'increment', increment_by, "
        "'cycle', cycle, 'cache', cache_size) ORDER BY sequencename) "
        "FROM pg_sequences WHERE schemaname = 'public'), '[]'::json), "
        "'views', COALESCE((SELECT json_agg(json_build_object('name', viewname, 'definition', definition) "
        "ORDER BY viewname) FROM pg_views WHERE schemaname = 'public'), '[]'::json), "
        "'types', COALESCE((SELECT json_agg(json_build_object("
        "'name', typ.typname, 'kind', typ.typtype, 'enum_labels', (SELECT json_agg(val.enumlabel "
        "ORDER BY val.enumsortorder) FROM pg_enum val WHERE val.enumtypid = typ.oid)) "
        "ORDER BY typ.typname) FROM pg_type typ JOIN pg_namespace ns ON ns.oid = typ.typnamespace "
        "WHERE ns.nspname = 'public' AND typ.typtype = 'e'), '[]'::json), "
        "'extensions', COALESCE((SELECT json_agg(json_build_object('name', extname, 'version', extversion) "
        "ORDER BY extname) FROM pg_extension), '[]'::json))"
        ")::text"
    )
    result = _run_postgres(
        ["psql", "--no-psqlrc", "--tuples-only", "--no-align", "--dbname", _libpq_url(database_url), "--command", query],
        timeout=180, database_url=database_url,
    )
    metadata = json.loads(result.stdout.strip())
    metadata["schema_signature"] = _schema_signature(metadata["schema_inventory"])
    return metadata


def _schema_signature(schema_inventory: dict) -> str:
    """Return a stable digest over schema structure, excluding data and ownership."""
    canonical = json.dumps(schema_inventory, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _available_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _validate_restore_metadata(restored: dict, expected: dict) -> None:
    if restored["row_counts"] != expected["row_counts"]:
        raise RuntimeError(
            "Restore validation failed: row counts differ "
            f"(source={expected['row_counts']}, restored={restored['row_counts']})"
        )
    if restored["alembic_versions"] != expected["alembic_versions"]:
        raise RuntimeError("Restore validation failed: database migration versions differ")
    if restored.get("schema_signature") != expected.get("schema_signature"):
        raise RuntimeError("Restore validation failed: public schema signature differs")
    expected_legal = expected.get("legal_content_checks") or {}
    restored_legal = restored.get("legal_content_checks") or {}
    required_checks = ("civil_code_exists", "art389_node_exists", "art389_change_exists")
    if (any(expected_legal.get(key) is not True for key in required_checks)
            or not expected_legal.get("art389_text_md5")):
        raise RuntimeError("Restore validation failed: source is missing required Civil Code Article 389 records")
    if restored_legal != expected_legal:
        raise RuntimeError("Restore validation failed: critical legal record checks differ")


def _verify_restore(dump_path: Path, expected: dict) -> dict:
    """Restore into an isolated temporary local PostgreSQL and compare core row counts."""
    initdb = shutil.which("initdb")
    pg_ctl = shutil.which("pg_ctl")
    if not initdb or not pg_ctl:
        raise RuntimeError("PostgreSQL server tools are required for restore verification")
    temp_root = Path(tempfile.mkdtemp(prefix="leiaberta-restore-check-"))
    data_dir = temp_root / "data"
    server_log = temp_root / "postgres-restore.log"
    port = _available_port()
    server_started = False
    try:
        _run_postgres(
            [initdb, "--pgdata", str(data_dir), "--username=postgres", "--auth-local=trust",
             "--auth-host=trust", "--no-sync", "--encoding=UTF8"],
            timeout=180,
        )
        _run_postgres(
            [pg_ctl, "--pgdata", str(data_dir), "--options",
             f"-h 127.0.0.1 -p {port} -F -c shared_buffers=32MB -c max_connections=20 "
             "-c checkpoint_timeout=1h -c max_wal_size=4GB "
             "-c maintenance_work_mem=128MB -c synchronous_commit=off",
             "--log", str(server_log), "--timeout", "120", "--wait", "start"],
            timeout=180,
        )
        server_started = True
        local_url = f"postgresql://postgres@127.0.0.1:{port}/postgres"
        restore_started = time.monotonic()
        _run_postgres(
            ["pg_restore", "--jobs=2", "--exit-on-error", "--no-owner", "--no-privileges",
             "--dbname", local_url, str(dump_path)],
            timeout=3600,
        )
        restore_duration_seconds = round(time.monotonic() - restore_started, 3)
        restored = _db_metadata(local_url)
        _validate_restore_metadata(restored, expected)
        restored["restore_duration_seconds"] = restore_duration_seconds
        return restored
    except Exception as exc:
        detail = server_log.read_text(encoding="utf-8", errors="replace")[-4000:] if server_log.exists() else ""
        if detail:
            raise RuntimeError(f"{exc}; local PostgreSQL startup log: {detail}") from exc
        raise
    finally:
        cleanup_safe = True
        if server_started or (data_dir / "postmaster.pid").exists():
            try:
                stopped = subprocess.run(
                    [pg_ctl, "--pgdata", str(data_dir), "--mode=fast", "--wait", "stop"],
                    check=False, capture_output=True, text=True, timeout=60,
                )
                cleanup_safe = stopped.returncode == 0 and not (data_dir / "postmaster.pid").exists()
            except subprocess.TimeoutExpired:
                cleanup_safe = False
        if cleanup_safe:
            shutil.rmtree(temp_root, ignore_errors=True)
        else:
            logger.error("isolated_restore_cleanup_incomplete temp_path=%s", temp_root)


def _s3_client():
    import boto3
    from botocore.config import Config

    return boto3.client(
        "s3",
        endpoint_url=_required_env("BACKUP_S3_ENDPOINT"),
        aws_access_key_id=_required_env("BACKUP_S3_ACCESS_KEY_ID"),
        aws_secret_access_key=_required_env("BACKUP_S3_SECRET_ACCESS_KEY"),
        region_name=_required_env("BACKUP_S3_REGION"),
        config=Config(s3={"addressing_style": os.getenv("BACKUP_S3_ADDRESSING_STYLE", "path")}),
    )


def _apply_retention(client, bucket: str, prefix: str, retention_days: int, now: datetime) -> int:
    cutoff = now - timedelta(days=retention_days)
    removed = 0
    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for item in page.get("Contents", []):
            if item["LastModified"] < cutoff:
                client.delete_object(Bucket=bucket, Key=item["Key"])
                removed += 1
    return removed


def _verify_uploaded_dump(client, bucket: str, key: str, expected_size: int, expected_sha256: str) -> dict:
    """Read the uploaded object sequentially and verify its actual bytes, not only ETag/metadata."""
    head = client.head_object(Bucket=bucket, Key=key)
    actual_size = int(head.get("ContentLength", -1))
    if actual_size != expected_size:
        raise RuntimeError(f"Uploaded dump size mismatch: expected {expected_size}, received {actual_size}")
    metadata_sha = (head.get("Metadata") or {}).get("sha256")
    if metadata_sha and metadata_sha != expected_sha256:
        raise RuntimeError("Uploaded dump checksum metadata mismatch")
    response = client.get_object(Bucket=bucket, Key=key)
    body = response["Body"]
    digest = hashlib.sha256()
    read_size = 0
    try:
        while chunk := body.read(1024 * 1024):
            digest.update(chunk)
            read_size += len(chunk)
    finally:
        close = getattr(body, "close", None)
        if close:
            close()
    actual_sha = digest.hexdigest()
    if read_size != expected_size or actual_sha != expected_sha256:
        raise RuntimeError(
            f"Uploaded dump byte verification failed: expected {expected_size}/{expected_sha256}, "
            f"received {read_size}/{actual_sha}"
        )
    return {"size_bytes": read_size, "sha256": actual_sha}


def _verify_uploaded_manifest(client, bucket: str, key: str, expected_bytes: bytes) -> str:
    response = client.get_object(Bucket=bucket, Key=key)
    body = response["Body"]
    try:
        actual_bytes = body.read()
    finally:
        close = getattr(body, "close", None)
        if close:
            close()
    expected_sha = hashlib.sha256(expected_bytes).hexdigest()
    if actual_bytes != expected_bytes:
        raise RuntimeError("Uploaded backup manifest read-back mismatch")
    return expected_sha


def run_backup() -> dict:
    database_url = _required_env("DATABASE_URL")
    bucket = _required_env("BACKUP_S3_BUCKET")
    retention_days = max(7, int(os.getenv("BACKUP_RETENTION_DAYS", "30")))
    verify_restore = os.getenv("BACKUP_VERIFY_RESTORE", "0").strip().lower() in {"1", "true", "yes"}
    now = datetime.now(timezone.utc)
    prefix = os.getenv("BACKUP_S3_PREFIX", "postgres/leiaberta-production/").strip("/") + "/"
    timestamp = now.strftime("%Y%m%dT%H%M%SZ")
    suffix = uuid.uuid4().hex[:8]
    dump_key = f"{prefix}{timestamp}-{suffix}.dump"
    manifest_key = f"{dump_key}.json"
    logger.info("postgres_backup_started timestamp=%s restore_verification=%s", timestamp, verify_restore)
    expected = _db_metadata(database_url)
    with tempfile.TemporaryDirectory(prefix="leiaberta-pg-backup-") as temp_dir:
        dump_path = Path(temp_dir) / "leiaberta.dump"
        _run_postgres(
            ["pg_dump", "--format=custom", "--compress=6", "--no-owner", "--no-privileges",
             "--dbname", _libpq_url(database_url), "--file", str(dump_path)],
            timeout=7200, database_url=database_url,
        )
        checksum = _sha256_file(dump_path)
        restored = _verify_restore(dump_path, expected) if verify_restore else None
        client = _s3_client()
        client.upload_file(str(dump_path), bucket, dump_key,
                           ExtraArgs={"ContentType": "application/vnd.postgresql.custom",
                                      "Metadata": {"sha256": checksum}})
        uploaded = _verify_uploaded_dump(client, bucket, dump_key, dump_path.stat().st_size, checksum)
        manifest = {
            "created_at": now.isoformat(), "database": "leiaberta-production",
            "dump_key": dump_key, "size_bytes": dump_path.stat().st_size,
            "sha256": checksum, "source": expected,
            "restore_verified": restored is not None,
            "restore_validation": restored,
            "uploaded_object_verified": True,
            "uploaded_object_sha256": uploaded["sha256"],
        }
        manifest_bytes = json.dumps(manifest, ensure_ascii=False, sort_keys=True).encode()
        client.put_object(Bucket=bucket, Key=manifest_key,
                          Body=manifest_bytes,
                          ContentType="application/json")
        manifest_sha256 = _verify_uploaded_manifest(client, bucket, manifest_key, manifest_bytes)
    # Retention is destructive. Never prune known-good history based on a run that
    # has not passed an isolated restore drill.
    if restored is not None:
        removed = _apply_retention(client, bucket, prefix, retention_days, now)
        retention_skipped = False
    else:
        removed = 0
        retention_skipped = True
    manifest["manifest_sha256"] = manifest_sha256
    logger.info(
        "postgres_backup_finished key=%s bytes=%s sha256=%s manifest_sha256=%s "
        "restore_verified=%s uploaded_object_verified=true expired_objects_removed=%s retention_skipped=%s",
        dump_key, manifest["size_bytes"], checksum, manifest_sha256,
        manifest["restore_verified"], removed, retention_skipped,
    )
    return manifest


if __name__ == "__main__":
    run_backup()

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
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import boto3
from botocore.config import Config


logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(message)s")
logger = logging.getLogger("leiaberta.backup")
ROW_COUNT_TABLES = (
    "laws", "law_versions", "legal_nodes", "history_events", "source_snapshots",
    "source_registry", "hydration_jobs", "job_outbox",
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
    try:
        result = subprocess.run(args, check=False, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        detail = exc.stderr or exc.stdout or ""
        if isinstance(detail, bytes):
            detail = detail.decode("utf-8", errors="replace")
        detail = str(detail).strip()
        if database_url:
            detail = detail.replace(database_url, "[DATABASE_URL]")
        suffix = f": {detail[:1000]}" if detail else ""
        raise RuntimeError(f"{Path(args[0]).name} timed out after {timeout} seconds{suffix}") from None
    if result.returncode:
        detail = result.stderr.strip()
        if database_url:
            detail = detail.replace(database_url, "[DATABASE_URL]")
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
        "'alembic_versions', COALESCE((SELECT json_agg(version_num ORDER BY version_num) "
        "FROM public.alembic_version), '[]'::json))::text"
    )
    result = _run_postgres(
        ["psql", "--no-psqlrc", "--tuples-only", "--no-align", "--dbname", _libpq_url(database_url), "--command", query],
        timeout=180, database_url=database_url,
    )
    return json.loads(result.stdout.strip())


def _available_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


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
             f"-h 127.0.0.1 -p {port} -F -c shared_buffers=32MB -c max_connections=20",
             "--log", str(server_log), "--timeout", "120", "--wait", "start"],
            timeout=180,
        )
        server_started = True
        local_url = f"postgresql://postgres@127.0.0.1:{port}/postgres"
        _run_postgres(
            ["pg_restore", "--exit-on-error", "--no-owner", "--no-privileges", "--dbname", local_url, str(dump_path)],
            timeout=3600,
        )
        restored = _db_metadata(local_url)
        if restored["row_counts"] != expected["row_counts"]:
            raise RuntimeError(
                "Restore validation failed: row counts differ "
                f"(source={expected['row_counts']}, restored={restored['row_counts']})"
            )
        if restored["alembic_versions"] != expected["alembic_versions"]:
            raise RuntimeError("Restore validation failed: database migration versions differ")
        return restored
    except Exception as exc:
        detail = server_log.read_text(encoding="utf-8", errors="replace")[-4000:] if server_log.exists() else ""
        if detail:
            raise RuntimeError(f"{exc}; local PostgreSQL startup log: {detail}") from exc
        raise
    finally:
        if server_started or (data_dir / "postmaster.pid").exists():
            subprocess.run([pg_ctl, "--pgdata", str(data_dir), "--mode=fast", "--wait", "stop"],
                           check=False, capture_output=True, text=True, timeout=30)
        shutil.rmtree(temp_root, ignore_errors=True)


def _s3_client():
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
        subprocess.run(
            ["pg_dump", "--format=custom", "--compress=6", "--no-owner", "--no-privileges",
             "--dbname", _libpq_url(database_url), "--file", str(dump_path)],
            check=True, capture_output=True, text=True, timeout=7200,
        )
        checksum = _sha256_file(dump_path)
        restored = _verify_restore(dump_path, expected) if verify_restore else None
        client = _s3_client()
        client.upload_file(str(dump_path), bucket, dump_key,
                           ExtraArgs={"ContentType": "application/vnd.postgresql.custom"})
        manifest = {
            "created_at": now.isoformat(), "database": "leiaberta-production",
            "dump_key": dump_key, "size_bytes": dump_path.stat().st_size,
            "sha256": checksum, "source": expected,
            "restore_verified": restored is not None,
            "restore_validation": restored,
        }
        client.put_object(Bucket=bucket, Key=manifest_key,
                          Body=json.dumps(manifest, ensure_ascii=False, sort_keys=True).encode(),
                          ContentType="application/json")
    removed = _apply_retention(client, bucket, prefix, retention_days, now)
    logger.info("postgres_backup_finished key=%s bytes=%s sha256=%s restore_verified=%s expired_objects_removed=%s",
                dump_key, manifest["size_bytes"], checksum, manifest["restore_verified"], removed)
    return manifest


if __name__ == "__main__":
    run_backup()

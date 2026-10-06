"""Restore one pre-verified LeiAberta dump into an isolated Railway Postgres."""
from __future__ import annotations

import hashlib
import json
import logging
import os
import subprocess
import tempfile
from pathlib import Path

import boto3
from botocore.config import Config


logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(message)s")
logger = logging.getLogger("leiaberta.restore")
EXPECTED_TABLES = (
    "laws", "law_versions", "legal_nodes", "history_events", "source_snapshots",
    "source_registry", "hydration_jobs", "job_outbox",
)
REQUIRED_SCHEMA_TABLES = {
    "alembic_version", "history_events", "hydration_jobs", "job_outbox", "jurisdictions",
    "law_changes", "law_versions", "laws", "legal_nodes", "senate_proceedings",
    "source_registry", "source_snapshots",
}
EXPECTED_KEY = "postgres/leiaberta-production/20261005T091036Z-3bc83b83.dump"
EXPECTED_BYTES = 247_073_141
EXPECTED_SHA256 = "d3afe0383f0b5b28124317090ce3fc16bb6acaa287f11b466ea2394774770190"
MAX_SOURCE_DB_BYTES = 2_500_000_000


def required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required configuration: {name}")
    return value


def run(args: list[str], *, timeout: int = 300) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(args, check=False, capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        detail = result.stderr.strip().replace(required("DATABASE_URL"), "[DATABASE_URL]")
        raise RuntimeError(f"{Path(args[0]).name} failed ({result.returncode}): {detail[:1500]}")
    return result


def database_url() -> str:
    return required("DATABASE_URL").replace("postgresql+psycopg://", "postgresql://", 1)


def s3_client():
    return boto3.client(
        "s3",
        endpoint_url=required("BACKUP_S3_ENDPOINT"),
        aws_access_key_id=required("BACKUP_S3_ACCESS_KEY_ID"),
        aws_secret_access_key=required("BACKUP_S3_SECRET_ACCESS_KEY"),
        region_name=os.getenv("BACKUP_S3_REGION", "auto"),
        config=Config(s3={"addressing_style": os.getenv("BACKUP_S3_ADDRESSING_STYLE", "path")}),
    )


def read_manifest(client, bucket: str) -> dict:
    key = EXPECTED_KEY + ".json"
    response = client.get_object(Bucket=bucket, Key=key)
    manifest = json.loads(response["Body"].read())
    checks = {
        "dump_key": manifest.get("dump_key") == EXPECTED_KEY,
        "size_bytes": manifest.get("size_bytes") == EXPECTED_BYTES,
        "sha256": manifest.get("sha256") == EXPECTED_SHA256,
        "restore_verified": manifest.get("restore_verified") is True,
    }
    failed = [name for name, okay in checks.items() if not okay]
    if failed:
        raise RuntimeError(f"Backup manifest mismatch: {', '.join(failed)}")
    source = manifest.get("source") or {}
    if not source.get("row_counts") or not source.get("alembic_versions"):
        raise RuntimeError("Backup manifest lacks row-count or migration-version evidence")
    try:
        db_size = int(source["database_size_bytes"])
        version_num = int(source["server_version_num"])
    except (KeyError, TypeError, ValueError):
        raise RuntimeError("Backup manifest lacks valid database size or server version") from None
    if version_num // 10000 != 18:
        raise RuntimeError(f"Backup PostgreSQL major version {version_num // 10000} does not match restore image major 18")
    if db_size > MAX_SOURCE_DB_BYTES:
        raise RuntimeError(
            f"Restore stopped before import: source database is {db_size} bytes; "
            f"the 5 GB blue volume safety limit is {MAX_SOURCE_DB_BYTES} bytes"
        )
    logger.info(
        "restore_preflight_passed key=%s bytes=%s sha256=%s source_db_bytes=%s postgres_major=%s "
        "source_row_counts=%s source_alembic_versions=%s",
        EXPECTED_KEY, EXPECTED_BYTES, EXPECTED_SHA256, db_size, version_num // 10000,
        json.dumps(source["row_counts"], sort_keys=True), json.dumps(source["alembic_versions"]),
    )
    return source


def metadata(url: str) -> dict:
    row_counts = ",".join(f"'{table}', (SELECT COUNT(*) FROM public.{table})" for table in EXPECTED_TABLES)
    query = (
        "SELECT json_build_object('server_version_num', current_setting('server_version_num'), "
        "'database_size_bytes', pg_database_size(current_database()), "
        "'schema_tables', COALESCE((SELECT json_agg(table_name ORDER BY table_name) "
        "FROM information_schema.tables WHERE table_schema='public' AND table_type='BASE TABLE'), '[]'::json), "
        "'public_constraint_count', (SELECT COUNT(*) FROM pg_constraint c "
        "JOIN pg_namespace n ON n.oid=c.connamespace WHERE n.nspname='public'), "
        f"'row_counts', json_build_object({row_counts}), "
        "'alembic_versions', COALESCE((SELECT json_agg(version_num ORDER BY version_num) "
        "FROM public.alembic_version), '[]'::json))::text"
    ).replace("'server_version_num'", "'server_version_num'")
    result = run(["psql", "--no-psqlrc", "--tuples-only", "--no-align", "--set=ON_ERROR_STOP=1",
                  "--dbname", url, "--command", query], timeout=180)
    return json.loads(result.stdout.strip())


def main() -> None:
    client = s3_client()
    bucket = required("BACKUP_S3_BUCKET")
    source = read_manifest(client, bucket)
    url = database_url()

    verify_only = os.getenv("RESTORE_VERIFY_ONLY", "0").strip().lower() in {"1", "true", "yes"}
    if not verify_only:
        empty = run([
            "psql", "--no-psqlrc", "--tuples-only", "--no-align", "--set=ON_ERROR_STOP=1",
            "--dbname", url, "--command",
            "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public'",
        ], timeout=60)
        if int(empty.stdout.strip() or "0") != 0:
            raise RuntimeError("Restore stopped: target public schema is not empty")

        with tempfile.TemporaryDirectory(prefix="leiaberta-blue-restore-") as temp_dir:
            dump_path = Path(temp_dir) / "production.dump"
            response = client.get_object(Bucket=bucket, Key=EXPECTED_KEY)
            if response.get("ContentLength") != EXPECTED_BYTES:
                raise RuntimeError(f"Dump object ContentLength mismatch: {response.get('ContentLength')}")
            digest = hashlib.sha256()
            size = 0
            with dump_path.open("wb") as output:
                body = response["Body"]
                while chunk := body.read(1024 * 1024):
                    digest.update(chunk)
                    size += len(chunk)
                    output.write(chunk)
            if size != EXPECTED_BYTES or digest.hexdigest() != EXPECTED_SHA256:
                raise RuntimeError(f"Downloaded dump verification failed: bytes={size}, sha256={digest.hexdigest()}")
            logger.info("dump_integrity_verified key=%s bytes=%s sha256=%s", EXPECTED_KEY, size, digest.hexdigest())

            run(["pg_restore", "--exit-on-error", "--no-owner", "--no-privileges", "--dbname", url,
                 str(dump_path)], timeout=7200)

    restored = metadata(url)
    expected_counts = {table: int(source["row_counts"][table]) for table in EXPECTED_TABLES}
    if restored["row_counts"] != expected_counts:
        raise RuntimeError(f"Restore row-count mismatch: expected={expected_counts}; actual={restored['row_counts']}")
    expected_versions = sorted(source["alembic_versions"])
    actual_versions = sorted(restored["alembic_versions"])
    if actual_versions != expected_versions:
        raise RuntimeError(f"Alembic version mismatch: expected={expected_versions}; actual={actual_versions}")
    missing_schema = sorted(REQUIRED_SCHEMA_TABLES.difference(restored["schema_tables"]))
    if missing_schema or int(restored["public_constraint_count"]) == 0:
        raise RuntimeError(
            f"Restore schema validation failed: missing_tables={missing_schema}; "
            f"constraints={restored['public_constraint_count']}"
        )

    law = run([
        "psql", "--no-psqlrc", "--tuples-only", "--no-align", "--set=ON_ERROR_STOP=1",
        "--dbname", url, "--command",
        "SELECT COUNT(*) FROM public.laws WHERE slug='10406-2002'",
    ], timeout=60)
    article = run([
        "psql", "--no-psqlrc", "--tuples-only", "--no-align", "--set=ON_ERROR_STOP=1",
        "--dbname", url, "--command",
        "SELECT COUNT(*) FROM public.legal_nodes WHERE law_slug='10406-2002' AND node_id='art:389' AND length(text)>0",
    ], timeout=60)
    if int(law.stdout.strip() or "0") != 1 or int(article.stdout.strip() or "0") < 1:
        raise RuntimeError("Critical-data validation failed for Código Civil 10.406/2002, art. 389")

    logger.info(
        "restore_validation_passed database_size_bytes=%s schema_tables=%s public_constraints=%s "
        "row_counts=%s alembic_versions=%s civil_code_present=true article_389_present=true",
        restored["database_size_bytes"], json.dumps(restored["schema_tables"]),
        restored["public_constraint_count"], json.dumps(restored["row_counts"], sort_keys=True),
        json.dumps(actual_versions),
    )


if __name__ == "__main__":
    main()

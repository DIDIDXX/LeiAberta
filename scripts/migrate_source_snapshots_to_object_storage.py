"""Migrate legacy source snapshots to S3 in resumable, verified batches.

The default is a full dry-run. ``--apply`` writes one bounded SQL transaction
per batch and saves an atomic local checkpoint after each committed batch.
The checkpoint contains only IDs and aggregate metrics, never credentials,
source URLs, or legal document bytes. ``raw_body`` is never modified.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import SourceSnapshot
from app.storage.source_snapshots import SourceSnapshotObjectStore

CHECKPOINT_VERSION = 1
MAX_BATCH_SIZE = 100
MAX_RETRIES = 5


class _MigrationUploadError(RuntimeError):
    def __init__(self, error_type: str, attempts: int) -> None:
        super().__init__(error_type)
        self.error_type = error_type
        self.attempts = attempts


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _checkpoint_target(path: str | Path) -> Path:
    target = Path(path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def _read_checkpoint(path: str | Path) -> dict[str, Any] | None:
    target = _checkpoint_target(path)
    if not target.exists():
        return None
    try:
        value = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Could not read migration checkpoint {target}") from exc
    if not isinstance(value, dict) or value.get("version") != CHECKPOINT_VERSION:
        raise ValueError("Unsupported source snapshot migration checkpoint version")
    if not isinstance(value.get("identity"), dict) or not isinstance(value.get("stats"), dict):
        raise ValueError("Invalid source snapshot migration checkpoint structure")
    if not isinstance(value.get("cursor"), int) or not isinstance(value.get("max_id"), int):
        raise ValueError("Invalid source snapshot migration checkpoint cursor")
    return value


def _write_checkpoint(path: str | Path, value: dict[str, Any]) -> None:
    target = _checkpoint_target(path)
    temp_name = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=target.parent,
                                         prefix=f".{target.name}.", suffix=".tmp", delete=False) as stream:
            temp_name = stream.name
            json.dump(value, stream, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, target)
        # Ensure the rename itself is durable where directory fsync is supported.
        try:
            directory_fd = os.open(target.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except OSError:
            pass
    finally:
        if temp_name and os.path.exists(temp_name):
            os.unlink(temp_name)


def _initial_totals(session: Session) -> dict[str, int]:
    max_id = int(session.scalar(select(func.coalesce(func.max(SourceSnapshot.id), 0))) or 0)
    total_rows = int(session.scalar(select(func.count(SourceSnapshot.id)).where(SourceSnapshot.id <= max_id)) or 0)
    existing_pointers = int(session.scalar(select(func.count(SourceSnapshot.id)).where(
        SourceSnapshot.id <= max_id,
        SourceSnapshot.object_key.is_not(None),
        SourceSnapshot.storage_backend == "s3",
    )) or 0)
    pending = int(session.scalar(select(func.count(SourceSnapshot.id)).where(
        SourceSnapshot.id <= max_id, SourceSnapshot.object_key.is_(None)
    )) or 0)
    return {"max_id": max_id, "total_rows": total_rows,
            "existing_pointers": existing_pointers, "pending_at_start": pending}


def _empty_stats() -> dict[str, Any]:
    return {
        "batches": 0,
        "selected": 0,
        "selected_bytes": 0,
        "verified": 0,
        "uploaded_objects": 0,
        "reused_objects": 0,
        "raw_bytes": 0,
        "referenced_stored_bytes": 0,
        "bucket_bytes_added": 0,
        "attempts": 0,
        "failures": 0,
        "invalid": [],
    }


def _merge_stats(total: dict[str, Any], batch: dict[str, Any]) -> None:
    for name in ("batches", "selected", "selected_bytes", "verified", "uploaded_objects", "reused_objects",
                 "raw_bytes", "referenced_stored_bytes", "bucket_bytes_added", "attempts", "failures"):
        total[name] = int(total.get(name, 0)) + int(batch.get(name, 0))
    known_invalid = {int(item["id"]) for item in total.get("invalid", [])}
    for item in batch.get("invalid", []):
        if int(item["id"]) not in known_invalid:
            total.setdefault("invalid", []).append(item)
            known_invalid.add(int(item["id"]))


def _put_with_retries(store, body: bytes, checksum: str, content_type: str,
                      max_retries: int, retry_delay: float) -> tuple[Any, int]:
    attempts = 0
    for retry in range(max_retries + 1):
        attempts += 1
        try:
            return store.put_verified(body, checksum, content_type=content_type), attempts
        except Exception as exc:
            if retry >= max_retries:
                raise _MigrationUploadError(type(exc).__name__, attempts) from exc
            if retry_delay > 0:
                time.sleep(min(retry_delay * (2 ** retry), 10.0))
    raise AssertionError("retry loop exhausted without returning or raising")


def migrate_batch(*, session: Session, after_id: int = 0, max_id: int | None = None,
                  batch_size: int = 25, apply: bool = False, store=None,
                  max_batch_bytes: int = 64 * 1024 * 1024,
                  max_retries: int = 3, retry_delay: float = 0.0) -> dict[str, Any]:
    """Migrate at most ``batch_size`` rows; caller advances its checkpoint only on success."""
    if batch_size < 1 or batch_size > MAX_BATCH_SIZE:
        raise ValueError(f"batch_size must be between 1 and {MAX_BATCH_SIZE}")
    if max_batch_bytes < 1:
        raise ValueError("max_batch_bytes must be >= 1")
    if max_retries < 0 or max_retries > MAX_RETRIES:
        raise ValueError(f"max_retries must be between 0 and {MAX_RETRIES}")
    if apply and store is None:
        raise ValueError("apply requires a configured source snapshot object store")

    query = select(SourceSnapshot.id, func.length(SourceSnapshot.raw_body)).where(
        SourceSnapshot.id > after_id, SourceSnapshot.object_key.is_(None)
    )
    if max_id is not None:
        query = query.where(SourceSnapshot.id <= max_id)
    candidates = session.execute(query.order_by(SourceSnapshot.id).limit(batch_size))
    snapshot_ids: list[int] = []
    selected_bytes = 0
    for snapshot_id, body_size in candidates:
        row_size = int(body_size or 0)
        if snapshot_ids and selected_bytes + row_size > max_batch_bytes:
            break
        # A single object larger than the byte budget is allowed alone so its
        # ID cannot permanently starve later rows; memory stays bounded to one body.
        snapshot_ids.append(int(snapshot_id))
        selected_bytes += row_size
    snapshots_count = len(snapshot_ids)
    result: dict[str, Any] = {
        "mode": "apply" if apply else "dry-run",
        "selected": snapshots_count,
        "selected_bytes": selected_bytes,
        "verified": 0,
        "uploaded_objects": 0,
        "reused_objects": 0,
        "raw_bytes": 0,
        "referenced_stored_bytes": 0,
        "bucket_bytes_added": 0,
        "attempts": 0,
        "failures": 0,
        "invalid": [],
        "last_id": snapshot_ids[-1] if snapshot_ids else after_id,
        "updated": 0,
        "elapsed_seconds": 0.0,
    }
    started = time.monotonic()
    try:
        for snapshot_id in snapshot_ids:
            snapshot = session.get(SourceSnapshot, snapshot_id)
            if snapshot is None or snapshot.object_key is not None:
                # Concurrent pointer creation is benign; the final SQL audit is
                # authoritative and this ID can still advance past safely.
                continue
            if snapshot.raw_body is None:
                result["invalid"].append({"id": snapshot.id, "reason": "database_payload_missing"})
                continue
            body = bytes(snapshot.raw_body)
            actual_sha256 = hashlib.sha256(body).hexdigest()
            if actual_sha256 != snapshot.checksum:
                result["invalid"].append({"id": snapshot.id, "reason": "database_checksum_mismatch"})
                continue
            result["verified"] += 1
            result["raw_bytes"] += len(body)
            if apply:
                try:
                    ref, attempts = _put_with_retries(
                        store, body, snapshot.checksum, snapshot.raw_format or "application/octet-stream",
                        max_retries, retry_delay,
                    )
                except _MigrationUploadError as exc:
                    result["attempts"] += exc.attempts
                    result["failures"] += 1
                    raise
                result["attempts"] += attempts
                if ref.backend != "s3" or not ref.object_key:
                    raise RuntimeError("object store returned an invalid pointer")
                # Commit only after put_verified has read back and SHA-256 checked the object.
                snapshot.storage_backend = ref.backend
                snapshot.object_key = ref.object_key
                snapshot.size_bytes = ref.size_bytes
                result["updated"] += 1
                result["referenced_stored_bytes"] += ref.stored_size_bytes
                if ref.created:
                    result["uploaded_objects"] += 1
                    result["bucket_bytes_added"] += ref.stored_size_bytes
                else:
                    result["reused_objects"] += 1
                session.flush()
        if apply:
            session.commit()
    except Exception as exc:
        session.rollback()
        result["failure"] = {
            "id": getattr(snapshot, "id", None),
            "error_type": getattr(exc, "error_type", type(exc).__name__),
            "attempts": getattr(exc, "attempts", result["attempts"]),
            "retry_limit": max_retries,
        }
        result["elapsed_seconds"] = round(time.monotonic() - started, 3)
        return result
    result["elapsed_seconds"] = round(time.monotonic() - started, 3)
    return result


def _checkpoint_for_run(*, session: Session, store, checkpoint_path: str | Path,
                        reset: bool = False) -> dict[str, Any]:
    checkpoint = None if reset else _read_checkpoint(checkpoint_path)
    target_identity = {"bucket": store.bucket, "prefix": store.prefix,
                       "endpoint": getattr(store, "endpoint_identity", None)}
    if checkpoint is None:
        totals = _initial_totals(session)
        return {
            "version": CHECKPOINT_VERSION,
            "identity": target_identity,
            "created_at": _utc_now(),
            "updated_at": _utc_now(),
            "max_id": totals["max_id"],
            "total_rows_at_start": totals["total_rows"],
            "existing_pointers_at_start": totals["existing_pointers"],
            "pending_at_start": totals["pending_at_start"],
            "cursor": 0,
            "stats": _empty_stats(),
        }
    if checkpoint.get("identity") != target_identity:
        raise ValueError("Checkpoint bucket/prefix does not match configured object storage")
    return checkpoint


def run_migration(*, session: Session, store=None, apply: bool = False,
                  batch_size: int = 25,
                  max_batch_bytes: int = 64 * 1024 * 1024,
                  checkpoint_path: str | Path = ".cache/source-snapshot-migration.json",
                  max_batches: int | None = None, max_retries: int = 3,
                  retry_delay: float = 0.5, reset_checkpoint: bool = False,
                  on_batch: Callable[[dict[str, Any]], None] | None = None) -> dict[str, Any]:
    """Scan a fixed ID range in bounded transactions and checkpoint committed batches."""
    if apply and store is None:
        raise ValueError("apply requires a configured source snapshot object store")
    if batch_size < 1 or batch_size > MAX_BATCH_SIZE:
        raise ValueError(f"batch_size must be between 1 and {MAX_BATCH_SIZE}")
    if max_batches is not None and max_batches < 1:
        raise ValueError("max_batches must be >= 1")

    # Dry runs do not persist state or contact object storage.
    checkpoint = (_checkpoint_for_run(session=session, store=store, checkpoint_path=checkpoint_path,
                                      reset=reset_checkpoint) if apply else {
        "max_id": _initial_totals(session)["max_id"], "cursor": 0,
        "stats": _empty_stats(), "pending_at_start": None, "total_rows_at_start": None,
        "existing_pointers_at_start": None, "identity": None,
    })
    started = time.monotonic()
    batches_this_run = 0
    failure = None
    while max_batches is None or batches_this_run < max_batches:
        batch = migrate_batch(session=session, after_id=int(checkpoint["cursor"]),
                              max_id=int(checkpoint["max_id"]), batch_size=batch_size,
                              max_batch_bytes=max_batch_bytes,
                              apply=apply, store=store, max_retries=max_retries,
                              retry_delay=retry_delay)
        if batch.get("failure"):
            failure = batch["failure"]
            checkpoint["stats"]["failures"] = int(checkpoint["stats"].get("failures", 0)) + int(batch["failures"])
            checkpoint["stats"]["attempts"] = int(checkpoint["stats"].get("attempts", 0)) + int(batch["attempts"])
            if apply:
                checkpoint["updated_at"] = _utc_now()
                _write_checkpoint(checkpoint_path, checkpoint)
            break
        if batch["selected"] == 0:
            break
        _merge_stats(checkpoint["stats"], batch)
        batches_this_run += 1
        if apply:
            checkpoint["cursor"] = int(batch["last_id"])
            checkpoint["updated_at"] = _utc_now()
            _write_checkpoint(checkpoint_path, checkpoint)
        else:
            checkpoint["cursor"] = int(batch["last_id"])
        if on_batch:
            on_batch({"batch": batches_this_run, "cursor": checkpoint["cursor"], **batch})

    # Query completion against DB pointers rather than inferring it from the service/job status.
    max_id = int(checkpoint["max_id"])
    pending = int(session.scalar(select(func.count(SourceSnapshot.id)).where(
        SourceSnapshot.id <= max_id, SourceSnapshot.object_key.is_(None)
    )) or 0)
    pointed_s3 = int(session.scalar(select(func.count(SourceSnapshot.id)).where(
        SourceSnapshot.id <= max_id, SourceSnapshot.storage_backend == "s3",
        SourceSnapshot.object_key.is_not(None)
    )) or 0)
    pointer_inconsistencies = int(session.scalar(select(func.count(SourceSnapshot.id)).where(
        SourceSnapshot.id <= max_id,
        (SourceSnapshot.object_key.is_(None) & SourceSnapshot.storage_backend.is_not(None))
        | (SourceSnapshot.object_key.is_not(None)
           & (SourceSnapshot.storage_backend.is_(None) | (SourceSnapshot.storage_backend != "s3")))
        | (SourceSnapshot.object_key.is_not(None) & SourceSnapshot.size_bytes.is_(None)),
    )) or 0)
    unique_object_keys = int(session.scalar(select(func.count(func.distinct(SourceSnapshot.object_key))).where(
        SourceSnapshot.id <= max_id, SourceSnapshot.storage_backend == "s3",
        SourceSnapshot.object_key.is_not(None)
    )) or 0)
    pointed_raw_bytes = int(session.scalar(select(func.coalesce(func.sum(SourceSnapshot.size_bytes), 0)).where(
        SourceSnapshot.id <= max_id, SourceSnapshot.storage_backend == "s3",
        SourceSnapshot.object_key.is_not(None)
    )) or 0)
    complete = pending == 0 and pointer_inconsistencies == 0 and failure is None
    return {
        "mode": "apply" if apply else "dry-run",
        "status": "failed" if failure else ("complete" if complete else "partial"),
        "checkpoint": str(checkpoint_path) if apply else None,
        "cursor": int(checkpoint["cursor"]),
        "max_id": max_id,
        "total_rows_at_start": checkpoint.get("total_rows_at_start"),
        "pending_at_start": checkpoint.get("pending_at_start"),
        "existing_pointers_at_start": checkpoint.get("existing_pointers_at_start"),
        "pending_pointers_at_end": pending,
        "pointed_s3_rows_at_end": pointed_s3,
        "unique_s3_object_keys_at_end": unique_object_keys,
        "pointed_raw_bytes_at_end": pointed_raw_bytes,
        "pointer_inconsistencies_at_end": pointer_inconsistencies,
        "progress_percent": (round(100 * (1 - pending / max(1, int(checkpoint.get("pending_at_start") or pending))), 2)
                             if apply else None),
        "batches_this_run": batches_this_run,
        "stats": checkpoint["stats"],
        "failure": failure,
        "elapsed_seconds": round(time.monotonic() - started, 3),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="upload, verify, and record pointers; default is dry-run")
    parser.add_argument("--batch-size", type=int, default=25, help="maximum rows per SQL transaction (1-100)")
    parser.add_argument("--max-batch-bytes", type=int, default=64 * 1024 * 1024,
                        help="approximate maximum uncompressed bytes selected per SQL transaction")
    parser.add_argument("--checkpoint", default=".cache/source-snapshot-migration.json",
                        help="checkpoint path (set to a durable mounted path for restart recovery)")
    parser.add_argument("--max-batches", type=int,
                        help="stop after N batches (use with --apply to resume from checkpoint next time)")
    parser.add_argument("--max-retries", type=int, default=3, help="bounded attempts per object after the first (0-5)")
    parser.add_argument("--retry-delay", type=float, default=0.5, help="base seconds for exponential retry backoff")
    parser.add_argument("--reset-checkpoint", action="store_true",
                        help="start a fresh scan up to current max ID; DB pointers remain idempotently skipped")
    args = parser.parse_args()
    if args.retry_delay < 0:
        parser.error("--retry-delay must be >= 0")

    store = None
    if args.apply:
        store = SourceSnapshotObjectStore.from_env()
        if store is None:
            parser.error("--apply requires complete SOURCE_SNAPSHOT_S3_* configuration")
    with SessionLocal() as session:
        def report_batch(progress: dict[str, Any]) -> None:
            print(json.dumps({"event": "source_snapshot_migration_batch", **progress}, sort_keys=True), flush=True)

        report = run_migration(session=session, store=store, apply=args.apply,
                               batch_size=args.batch_size, checkpoint_path=args.checkpoint,
                               max_batch_bytes=args.max_batch_bytes,
                               max_batches=args.max_batches, max_retries=args.max_retries,
                               retry_delay=args.retry_delay, reset_checkpoint=args.reset_checkpoint,
                               on_batch=report_batch)
    print(json.dumps(report, sort_keys=True))
    if report["status"] != "complete":
        raise SystemExit(1)


if __name__ == "__main__":
    main()

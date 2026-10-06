"""Copy one bounded batch of source snapshots to object storage.

Dry-run is the default. Use --apply only after reviewing the report and
configuring the dedicated SOURCE_SNAPSHOT_S3_* settings. Each upload is read
back and SHA-256 checked before its database pointer is committed. raw_body is
never changed by this command.
"""
from __future__ import annotations

import argparse
import hashlib
import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import SourceSnapshot
from app.storage.source_snapshots import SourceSnapshotObjectStore


def migrate_batch(*, session: Session, after_id: int = 0, batch_size: int = 25,
                  apply: bool = False, store=None) -> dict:
    if batch_size < 1 or batch_size > 100:
        raise ValueError("batch_size must be between 1 and 100")
    if apply and store is None:
        raise ValueError("apply requires a configured source snapshot object store")

    snapshots = list(session.scalars(
        select(SourceSnapshot)
        .where(SourceSnapshot.id > after_id, SourceSnapshot.object_key.is_(None))
        .order_by(SourceSnapshot.id)
        .limit(batch_size)
    ))
    result = {
        "mode": "apply" if apply else "dry-run",
        "selected": len(snapshots),
        "verified": 0,
        "invalid": [],
        "total_bytes": 0,
        "last_id": snapshots[-1].id if snapshots else after_id,
        "updated": 0,
    }
    try:
        for snapshot in snapshots:
            body = bytes(snapshot.raw_body)
            actual_sha256 = hashlib.sha256(body).hexdigest()
            if actual_sha256 != snapshot.checksum:
                result["invalid"].append({"id": snapshot.id, "reason": "database_checksum_mismatch"})
                continue
            result["verified"] += 1
            result["total_bytes"] += len(body)
            if apply:
                object_ref = store.put_verified(body, snapshot.checksum, content_type=snapshot.raw_format)
                # put_verified reads the object back and verifies the payload
                # digest before this ORM row receives its pointer.
                snapshot.storage_backend = object_ref.backend
                snapshot.object_key = object_ref.object_key
                snapshot.size_bytes = object_ref.size_bytes
                result["updated"] += 1
        if apply:
            session.commit()
    except Exception:
        session.rollback()
        raise
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="upload, verify, and record pointers; default is dry-run")
    parser.add_argument("--batch-size", type=int, default=25, help="maximum rows per invocation (1-100; default 25)")
    parser.add_argument("--after-id", type=int, default=0, help="resume after this snapshot id; default 0")
    args = parser.parse_args()

    store = None
    if args.apply:
        store = SourceSnapshotObjectStore.from_env()
        if store is None:
            parser.error("--apply requires complete SOURCE_SNAPSHOT_S3_* configuration")
    with SessionLocal() as session:
        result = migrate_batch(session=session, after_id=args.after_id,
                               batch_size=args.batch_size, apply=args.apply, store=store)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()

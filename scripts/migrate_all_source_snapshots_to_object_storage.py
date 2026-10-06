"""Run bounded, resumable source-snapshot object migration batches.

This is an operational wrapper around the reviewed single-batch migration. It
never modifies raw_body or deletes data. Dry-run is the default; --apply must be
explicit. Each committed batch is idempotent and can be resumed by rerunning.
"""
from __future__ import annotations

import argparse
import json
import runpy
from pathlib import Path

from app.db import SessionLocal
from app.storage.source_snapshots import SourceSnapshotObjectStore


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="upload and verify each selected batch")
    parser.add_argument("--batch-size", type=int, default=100, help="1-100 snapshots per transaction")
    parser.add_argument("--after-id", type=int, default=0, help="resume after a prior batch cursor")
    args = parser.parse_args()
    if not 1 <= args.batch_size <= 100:
        parser.error("--batch-size must be between 1 and 100")
    store = SourceSnapshotObjectStore.from_env() if args.apply else None
    if args.apply and store is None:
        parser.error("--apply requires complete SOURCE_SNAPSHOT_S3_* configuration")

    module_path = Path(__file__).with_name("migrate_source_snapshots_to_object_storage.py")
    migrate_batch = runpy.run_path(str(module_path))["migrate_batch"]
    cursor = args.after_id
    totals = {"selected": 0, "verified": 0, "invalid": 0, "total_bytes": 0, "updated": 0, "batches": 0}
    while True:
        previous = cursor
        with SessionLocal() as session:
            result = migrate_batch(session=session, after_id=cursor, batch_size=args.batch_size,
                                   apply=args.apply, store=store)
        totals["batches"] += 1
        for key in ("selected", "verified", "total_bytes", "updated"):
            totals[key] += int(result[key])
        totals["invalid"] += len(result["invalid"])
        print(json.dumps({"batch": result}, sort_keys=True), flush=True)
        if result["invalid"]:
            raise SystemExit("Stopped on checksum-invalid rows; no raw_body data was changed.")
        if result["selected"] == 0:
            break
        cursor = int(result["last_id"])
        if cursor <= previous:
            raise RuntimeError("Migration cursor failed to advance")
        if result["selected"] < args.batch_size:
            break
    print(json.dumps({"migration_complete": totals, "mode": "apply" if args.apply else "dry-run",
                      "last_id": cursor}, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()

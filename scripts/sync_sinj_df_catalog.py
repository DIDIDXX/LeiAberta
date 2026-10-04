#!/usr/bin/env python3
"""Inspect or synchronize the complete official SINJ-DF norm catalog."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.catalog_sync.sinj_df import PAGE_SIZE, fetch_catalog_page, parse_catalog_page, sync_sinj_df_catalog


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Read catalog pages without writing to the database.")
    parser.add_argument("--max-pages", type=int, default=1, help="Pages to sample in dry-run mode (default: 1).")
    parser.add_argument("--page-size", type=int, default=PAGE_SIZE, help=f"Page size from 1 to {PAGE_SIZE}.")
    parser.add_argument("--force", action="store_true", help="Refresh even when the catalog is recent.")
    args = parser.parse_args()
    if args.page_size < 1 or args.page_size > PAGE_SIZE or args.max_pages < 1:
        parser.error("--page-size e --max-pages devem ser positivos; page-size não pode exceder 5000.")
    if not args.dry_run:
        print(json.dumps(sync_sinj_df_catalog(force=args.force, page_size=args.page_size), ensure_ascii=False, indent=2))
        return 0

    first, source_url = fetch_catalog_page(0, size=args.page_size)
    expected = int(first["iTotalDisplayRecords"])
    pages = (expected + args.page_size - 1) // args.page_size
    sample_pages = min(args.max_pages, pages)
    count = 0
    types: dict[str, int] = {}
    for page_number in range(sample_pages):
        payload = first if page_number == 0 else fetch_catalog_page(page_number * args.page_size, size=args.page_size)[0]
        records = parse_catalog_page(payload)
        count += len(records)
        for record in records:
            types[record.law_type] = types.get(record.law_type, 0) + 1
    print(json.dumps({"source_url": source_url, "records_expected": expected, "pages_expected": pages,
                      "pages_read": sample_pages, "records_read": count,
                      "sample_type_counts": dict(sorted(types.items()))}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

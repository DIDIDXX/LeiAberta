"""Synchronize or inspect the official ALESP legislation catalog."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import inspect

from app.catalog_sync.alesp import ALESP_PAGE_SIZE, fetch_catalog_page, parse_catalog_page, sync_alesp_catalog
from app.db import engine


def dry_run(*, page_size: int, max_pages: int | None) -> dict:
    first, _url = fetch_catalog_page(0, size=page_size)
    expected_total = first["totalElements"]
    expected_pages = first["totalPages"]
    pages_to_read = min(expected_pages, max_pages or expected_pages)
    seen: set[str] = set()
    digest = hashlib.sha256()
    for page in range(pages_to_read):
        data = first if page == 0 else fetch_catalog_page(page, size=page_size)[0]
        if data["totalElements"] != expected_total or data["totalPages"] != expected_pages:
            raise ValueError("O total ALESP mudou durante o dry-run.")
        records = parse_catalog_page(data)
        for item in records:
            if item.remote_id in seen:
                raise ValueError(f"ID remoto ALESP repetido: {item.remote_id}")
            seen.add(item.remote_id)
            digest.update(item.remote_id.encode())
            digest.update(b"\n")
    complete = pages_to_read == expected_pages and len(seen) == expected_total
    return {"dry_run": True, "pages_read": pages_to_read, "pages_expected": expected_pages,
            "records_read": len(seen), "records_expected": expected_total, "complete": complete,
            "catalog_ids_sha256_partial_or_complete": digest.hexdigest()}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sincroniza o catálogo oficial de legislação da ALESP.")
    parser.add_argument("--force", action="store_true", help="Ignora a janela de frescor de sete dias.")
    parser.add_argument("--page-size", type=int, default=ALESP_PAGE_SIZE,
                        help=f"Itens por página (máximo {ALESP_PAGE_SIZE}).")
    parser.add_argument("--dry-run", action="store_true", help="Valida a paginação, sem persistir registros.")
    parser.add_argument("--max-pages", type=int, help="Limita o dry-run a uma amostra de páginas.")
    args = parser.parse_args()
    if args.dry_run:
        result = dry_run(page_size=args.page_size, max_pages=args.max_pages)
    else:
        inspector = inspect(engine)
        if not inspector.has_table("laws") or not inspector.has_table("source_registry"):
            raise SystemExit("Schema ausente. Execute `alembic upgrade head` antes da sincronização.")
        result = sync_alesp_catalog(force=args.force, page_size=args.page_size)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result.get("complete") is False and not args.dry_run:
        raise SystemExit(1)

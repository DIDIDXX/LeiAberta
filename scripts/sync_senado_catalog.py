import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import inspect
from app.db import engine
from app.catalog_sync.senado import TYPE_LABELS, sync_senado_law_catalog

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sincroniza catálogos normativos oficiais do Senado.")
    parser.add_argument("--type", dest="types", action="append", choices=tuple(TYPE_LABELS),
                        help="Tipo do Senado. Repita para vários tipos; por padrão sincroniza todos os tipos validados.")
    parser.add_argument("--force", action="store_true", help="Ignora a janela de frescor de 24 horas.")
    args = parser.parse_args()
    inspector = inspect(engine)
    if not inspector.has_table("laws") or "external_source_id" not in {column["name"] for column in inspector.get_columns("laws")}:
        raise SystemExit("Colunas externas ausentes. Execute `alembic upgrade head` antes da sincronização.")
    result = sync_senado_law_catalog(tuple(args.types or TYPE_LABELS), force=args.force)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result["errors"] and not result["synced"]:
        raise SystemExit(1)

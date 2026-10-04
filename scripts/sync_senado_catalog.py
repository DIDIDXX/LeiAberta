import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import inspect
from app.db import engine
from app.catalog_sync.senado import sync_senado_law_catalog

if __name__ == "__main__":
    argparse.ArgumentParser(description="Sincroniza o catálogo de leis federais do Senado.").parse_args()
    inspector = inspect(engine)
    if not inspector.has_table("laws") or "external_source_id" not in {column["name"] for column in inspector.get_columns("laws")}:
        raise SystemExit("Colunas externas ausentes. Execute `alembic upgrade head` antes da sincronização.")
    print(json.dumps(sync_senado_law_catalog(), ensure_ascii=False, indent=2))

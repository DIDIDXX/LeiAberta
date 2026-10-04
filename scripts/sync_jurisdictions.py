import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import inspect
from app.db import engine
from app.catalog_sync.ibge import sync_ibge_jurisdictions

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sincroniza o diretório territorial oficial do IBGE.")
    parser.add_argument("--force", action="store_true", help="Ignora a janela de frescor de 24 horas.")
    args = parser.parse_args()
    if not inspect(engine).has_table("jurisdictions"):
        raise SystemExit("Tabela jurisdictions ausente. Execute `alembic upgrade head` antes da sincronização.")
    print(json.dumps(sync_ibge_jurisdictions(force=args.force), ensure_ascii=False, indent=2))

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text

import app.db
from app.worker import wait_for_database_schema


def test_worker_waits_for_the_current_alembic_head(db_session, monkeypatch):
    config = Config("alembic.ini")
    head = ScriptDirectory.from_config(config).get_heads()[0]
    db_session.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"))
    db_session.execute(text("INSERT INTO alembic_version(version_num) VALUES (:head)"), {"head": head})
    db_session.commit()
    monkeypatch.setattr(app.db, "engine", db_session.get_bind())

    wait_for_database_schema(timeout=0.1, interval=0.01)

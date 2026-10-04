import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.models import Law, LegalNode


@pytest.fixture
def db_session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = Session()
    yield session
    session.close()
    Base.metadata.drop_all(engine)
    engine.dispose()


def law_row(slug="13709-2018", title="Lei Geral de Proteção de Dados Pessoais", number="13.709", year=2018,
            aliases=None):
    return Law(
        slug=slug, jurisdiction="federal", law_type="Lei", number=number, year=year, title=title,
        description="Norma federal de teste.", aliases=aliases or ["LGPD"],
        source_name="Presidência da República — Planalto", source_url="https://www.planalto.gov.br/",
        fetch_url="http://www.planalto.gov.br/", hot=True, materialization_status="ready",
        coverage={"official_source": "available", "structured_text": "available"},
    )


@pytest.fixture
def add_law():
    return law_row

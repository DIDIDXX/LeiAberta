"""Keep Senate source identity and signature dates on federal catalog records."""
from alembic import op
import sqlalchemy as sa
from datetime import date

revision = "20261004_0004"
down_revision = "20261004_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("laws", sa.Column("external_source_id", sa.String(96), nullable=True))
    op.add_column("laws", sa.Column("signed_at", sa.Date(), nullable=True))
    op.create_index("uq_laws_external_source_id", "laws", ["external_source_id"], unique=True)
    laws = sa.table("laws", sa.column("slug", sa.String), sa.column("published_at", sa.Date),
                    sa.column("coverage", sa.JSON))
    slugs = ["13709-2018", "12965-2014", "11340-2006", "8078-1990", "8069-1990",
             "14133-2021", "8429-1992", "lcp-135-2010", "constituicao-1988",
             "10406-2002", "2848-1940", "5172-1966", "5452-1943", "12527-2011"]
    connection = op.get_bind()
    for row in connection.execute(sa.select(laws.c.slug, laws.c.published_at, laws.c.coverage).where(laws.c.slug.in_(slugs))):
        if row.published_at is None:
            continue
        coverage = dict(row.coverage or {})
        coverage["legacy_catalog_date_unverified"] = row.published_at.isoformat()
        connection.execute(laws.update().where(laws.c.slug == row.slug).values(published_at=None, coverage=coverage))


def downgrade() -> None:
    laws = sa.table("laws", sa.column("slug", sa.String), sa.column("published_at", sa.Date),
                    sa.column("coverage", sa.JSON))
    connection = op.get_bind()
    for row in connection.execute(sa.select(laws.c.slug, laws.c.coverage)):
        coverage = dict(row.coverage or {})
        value = coverage.pop("legacy_catalog_date_unverified", None)
        if value:
            connection.execute(laws.update().where(laws.c.slug == row.slug).values(
                published_at=date.fromisoformat(value), coverage=coverage))
    op.drop_index("uq_laws_external_source_id", table_name="laws")
    op.drop_column("laws", "signed_at")
    op.drop_column("laws", "external_source_id")

"""Create an auditable national jurisdiction and source registry."""
from alembic import op
import sqlalchemy as sa

revision = "20261004_0003"
down_revision = "20261004_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "jurisdictions",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("name", sa.String(180), nullable=False),
        sa.Column("ibge_code", sa.String(12), unique=True),
        sa.Column("uf", sa.String(2)),
        sa.Column("parent_id", sa.String(96), sa.ForeignKey("jurisdictions.id")),
        sa.Column("legislature_eligible", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("territorial_status", sa.String(32), nullable=False, server_default="active"),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
    )
    for col in ("kind", "name", "uf", "parent_id"):
        op.create_index(f"ix_jurisdictions_{col}", "jurisdictions", [col])
    op.create_table(
        "source_registry",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("jurisdiction_id", sa.String(96), sa.ForeignKey("jurisdictions.id")),
        sa.Column("name", sa.String(180), nullable=False),
        sa.Column("adapter", sa.String(48), nullable=False),
        sa.Column("base_url", sa.Text(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="discovered"),
        sa.Column("scope", sa.JSON(), nullable=False),
        sa.Column("evidence_url", sa.Text(), nullable=False),
        sa.Column("last_checked_at", sa.DateTime(timezone=True)),
        sa.Column("last_error", sa.Text(), nullable=False, server_default=""),
    )
    op.create_index("ix_source_registry_jurisdiction_id", "source_registry", ["jurisdiction_id"])
    op.create_index("ix_source_registry_status", "source_registry", ["status"])


def downgrade() -> None:
    op.drop_index("ix_source_registry_status", table_name="source_registry")
    op.drop_index("ix_source_registry_jurisdiction_id", table_name="source_registry")
    op.drop_table("source_registry")
    for col in ("kind", "name", "uf", "parent_id"):
        op.drop_index(f"ix_jurisdictions_{col}", table_name="jurisdictions")
    op.drop_table("jurisdictions")

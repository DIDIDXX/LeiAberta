"""Persist Senate process, amendment and vote dossiers."""
from alembic import op
import sqlalchemy as sa

revision = "20261005_0010"
down_revision = "20261005_0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "senate_proceedings",
        sa.Column("law_slug", sa.String(length=96), sa.ForeignKey("laws.slug", ondelete="CASCADE"), primary_key=True),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="not_requested"),
        sa.Column("data", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=False, server_default=""),
    )
    op.create_index("ix_senate_proceedings_status", "senate_proceedings", ["status"])


def downgrade() -> None:
    op.drop_index("ix_senate_proceedings_status", table_name="senate_proceedings")
    op.drop_table("senate_proceedings")

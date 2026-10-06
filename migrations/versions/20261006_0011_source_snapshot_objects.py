"""Add optional object-storage pointers for immutable source snapshots.

Revision ID: 20261006_0011
Revises: 20261005_0010
"""
from alembic import op
import sqlalchemy as sa


revision = "20261006_0011"
down_revision = "20261005_0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # All fields are nullable and raw_body stays NOT NULL. This is additive and
    # permits old application versions and database-only snapshots to coexist.
    op.add_column("source_snapshots", sa.Column("storage_backend", sa.String(length=16), nullable=True))
    op.add_column("source_snapshots", sa.Column("object_key", sa.String(length=512), nullable=True))
    op.add_column("source_snapshots", sa.Column("size_bytes", sa.BigInteger(), nullable=True))


def downgrade() -> None:
    # Safe while raw_body is retained: dropping pointers only returns reads to
    # the database copy and leaves all legal source bytes intact.
    op.drop_column("source_snapshots", "size_bytes")
    op.drop_column("source_snapshots", "object_key")
    op.drop_column("source_snapshots", "storage_backend")

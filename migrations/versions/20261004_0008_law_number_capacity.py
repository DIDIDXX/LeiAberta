"""Allow full official identifiers such as judicial case numbers in catalogs."""
from alembic import op
import sqlalchemy as sa

revision = "20261004_0008"
down_revision = "20261004_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.alter_column("laws", "number", existing_type=sa.String(length=24), type_=sa.String(length=96))
    else:
        with op.batch_alter_table("laws") as batch:
            batch.alter_column("number", existing_type=sa.String(length=24), type_=sa.String(length=96))


def downgrade() -> None:
    too_long = op.get_bind().execute(sa.text("SELECT COUNT(*) FROM laws WHERE length(number) > 24")).scalar_one()
    if too_long:
        raise RuntimeError("Cannot downgrade: laws contains official identifiers longer than 24 characters.")
    if op.get_bind().dialect.name == "postgresql":
        op.alter_column("laws", "number", existing_type=sa.String(length=96), type_=sa.String(length=24))
    else:
        with op.batch_alter_table("laws") as batch:
            batch.alter_column("number", existing_type=sa.String(length=96), type_=sa.String(length=24))

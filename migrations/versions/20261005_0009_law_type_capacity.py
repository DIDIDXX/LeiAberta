"""Allow long official normative-class labels."""
from alembic import op
import sqlalchemy as sa

revision = "20261005_0009"
down_revision = "20261004_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.alter_column("laws", "law_type", existing_type=sa.String(length=48), type_=sa.String(length=128))
    else:
        with op.batch_alter_table("laws") as batch:
            batch.alter_column("law_type", existing_type=sa.String(length=48), type_=sa.String(length=128))


def downgrade() -> None:
    too_long = op.get_bind().execute(sa.text("SELECT COUNT(*) FROM laws WHERE length(law_type) > 48")).scalar_one()
    if too_long:
        raise RuntimeError("Cannot downgrade: laws contains normative-class labels longer than 48 characters.")
    if op.get_bind().dialect.name == "postgresql":
        op.alter_column("laws", "law_type", existing_type=sa.String(length=128), type_=sa.String(length=48))
    else:
        with op.batch_alter_table("laws") as batch:
            batch.alter_column("law_type", existing_type=sa.String(length=128), type_=sa.String(length=48))

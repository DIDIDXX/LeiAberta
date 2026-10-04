"""Index official number lookups across the expanded federal catalog."""
from alembic import op
import sqlalchemy as sa

revision = "20261004_0007"
down_revision = "20261004_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_laws_number", "laws", ["number"])


def downgrade() -> None:
    op.drop_index("ix_laws_number", table_name="laws")

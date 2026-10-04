"""Version source text and parser representations independently."""
from alembic import op

revision = "20261004_0005"
down_revision = "20261004_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("law_versions") as batch:
        batch.drop_constraint("uq_law_version_checksum", type_="unique")
        batch.create_unique_constraint("uq_law_version_checksum_parser", ["law_slug", "checksum", "parser_version"])


def downgrade() -> None:
    with op.batch_alter_table("law_versions") as batch:
        batch.drop_constraint("uq_law_version_checksum_parser", type_="unique")
        batch.create_unique_constraint("uq_law_version_checksum", ["law_slug", "checksum"])

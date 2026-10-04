"""Allow official source archives to exist before or without parsed versions."""
from alembic import op
import sqlalchemy as sa

revision = "20261004_0006"
down_revision = "20261004_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.drop_constraint("source_snapshots_version_id_fkey", "source_snapshots", type_="foreignkey")
        op.alter_column("source_snapshots", "version_id", existing_type=sa.Integer(), nullable=True)
        op.alter_column("source_snapshots", "raw_format", existing_type=sa.String(length=32), type_=sa.String(length=80))
        op.create_foreign_key("fk_source_snapshots_version_id_law_versions", "source_snapshots",
                              "law_versions", ["version_id"], ["id"], ondelete="SET NULL")
    else:
        naming = {"fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s"}
        with op.batch_alter_table("source_snapshots", recreate="always", naming_convention=naming) as batch:
            batch.drop_constraint("fk_source_snapshots_version_id_law_versions", type_="foreignkey")
            batch.alter_column("version_id", existing_type=sa.Integer(), nullable=True)
            batch.alter_column("raw_format", existing_type=sa.String(length=32), type_=sa.String(length=80))
            batch.create_foreign_key(
                "fk_source_snapshots_version_id_law_versions", "law_versions",
                ["version_id"], ["id"], ondelete="SET NULL",
            )


def downgrade() -> None:
    bind = op.get_bind()
    archived = bind.execute(sa.text("SELECT COUNT(*) FROM source_snapshots WHERE version_id IS NULL")).scalar_one()
    if archived:
        raise RuntimeError("Cannot downgrade: source_snapshots contains archives without parser versions.")
    if op.get_bind().dialect.name == "postgresql":
        op.drop_constraint("fk_source_snapshots_version_id_law_versions", "source_snapshots", type_="foreignkey")
        op.alter_column("source_snapshots", "version_id", existing_type=sa.Integer(), nullable=False)
        op.alter_column("source_snapshots", "raw_format", existing_type=sa.String(length=80), type_=sa.String(length=32))
        op.create_foreign_key("source_snapshots_version_id_fkey", "source_snapshots",
                              "law_versions", ["version_id"], ["id"], ondelete="CASCADE")
    else:
        naming = {"fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s"}
        with op.batch_alter_table("source_snapshots", recreate="always", naming_convention=naming) as batch:
            batch.drop_constraint("fk_source_snapshots_version_id_law_versions", type_="foreignkey")
            batch.alter_column("version_id", existing_type=sa.Integer(), nullable=False)
            batch.alter_column("raw_format", existing_type=sa.String(length=80), type_=sa.String(length=32))
            batch.create_foreign_key(
                "source_snapshots_version_id_fkey", "law_versions", ["version_id"], ["id"], ondelete="CASCADE",
            )

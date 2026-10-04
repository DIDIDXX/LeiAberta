"""Initial legislation catalog and provenance tables.

Revision ID: 20261004_0001
Revises:
Create Date: 2026-10-04
"""
from alembic import op
import sqlalchemy as sa

revision = "20261004_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "laws",
        sa.Column("slug", sa.String(96), primary_key=True),
        sa.Column("jurisdiction", sa.String(24), nullable=False, server_default="federal"),
        sa.Column("state_code", sa.String(2)),
        sa.Column("municipality", sa.String(120)),
        sa.Column("law_type", sa.String(48), nullable=False),
        sa.Column("number", sa.String(24), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(48), nullable=False, server_default="Em vigor"),
        sa.Column("published_at", sa.Date()),
        sa.Column("aliases", sa.JSON(), nullable=False),
        sa.Column("source_name", sa.String(120), nullable=False, server_default="Presidência da República — Planalto"),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("fetch_url", sa.Text(), nullable=False),
        sa.Column("hot", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("materialization_status", sa.String(24), nullable=False, server_default="catalog"),
        sa.Column("last_hydrated_at", sa.DateTime(timezone=True)),
        sa.Column("current_version_id", sa.Integer()),
        sa.Column("coverage", sa.JSON(), nullable=False),
    )
    op.create_index("ix_laws_jurisdiction", "laws", ["jurisdiction"])
    op.create_index("ix_laws_year", "laws", ["year"])
    op.create_index("ix_laws_title", "laws", ["title"])
    op.create_index("ix_laws_hot", "laws", ["hot"])
    op.create_index("ix_laws_materialization_status", "laws", ["materialization_status"])

    op.create_table(
        "law_versions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("law_slug", sa.String(96), sa.ForeignKey("laws.slug", ondelete="CASCADE"), nullable=False),
        sa.Column("version_name", sa.String(160), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("checksum", sa.String(64), nullable=False),
        sa.Column("parser_version", sa.String(32), nullable=False, server_default="1.0"),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("article_count", sa.Integer(), nullable=False, server_default="0"),
        sa.UniqueConstraint("law_slug", "checksum", name="uq_law_version_checksum"),
    )
    op.create_index("ix_law_versions_law_slug", "law_versions", ["law_slug"])
    op.create_index("ix_law_versions_checksum", "law_versions", ["checksum"])
    op.create_index("ix_law_versions_is_current", "law_versions", ["is_current"])

    op.create_table(
        "legal_nodes",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("law_slug", sa.String(96), sa.ForeignKey("laws.slug", ondelete="CASCADE"), nullable=False),
        sa.Column("version_id", sa.Integer(), sa.ForeignKey("law_versions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("node_id", sa.String(160), nullable=False),
        sa.Column("parent_node_id", sa.String(160)),
        sa.Column("node_type", sa.String(24), nullable=False),
        sa.Column("label", sa.String(64), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("source_note", sa.Text(), nullable=False, server_default=""),
        sa.Column("order_index", sa.Integer(), nullable=False),
        sa.UniqueConstraint("version_id", "node_id", name="uq_legal_node_version_id"),
    )
    for column in ("law_slug", "version_id", "node_id", "parent_node_id", "node_type", "order_index"):
        op.create_index(f"ix_legal_nodes_{column}", "legal_nodes", [column])

    op.create_table(
        "source_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("law_slug", sa.String(96), sa.ForeignKey("laws.slug", ondelete="CASCADE"), nullable=False),
        sa.Column("version_id", sa.Integer(), sa.ForeignKey("law_versions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("checksum", sa.String(64), nullable=False),
        sa.Column("raw_format", sa.String(32), nullable=False, server_default="text/html; charset=iso-8859-1"),
        sa.Column("raw_body", sa.LargeBinary(), nullable=False),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("law_slug", "checksum", name="uq_source_snapshot_checksum"),
    )
    op.create_index("ix_source_snapshots_law_slug", "source_snapshots", ["law_slug"])
    op.create_index("ix_source_snapshots_version_id", "source_snapshots", ["version_id"])
    op.create_index("ix_source_snapshots_checksum", "source_snapshots", ["checksum"])

    op.create_table(
        "law_changes",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("law_slug", sa.String(96), sa.ForeignKey("laws.slug", ondelete="CASCADE"), nullable=False),
        sa.Column("node_id", sa.String(160), nullable=False),
        sa.Column("change_type", sa.String(16), nullable=False, server_default="ADD"),
        sa.Column("summary", sa.String(300), nullable=False),
        sa.Column("changed_at", sa.Date()),
        sa.Column("source_law_label", sa.String(180), nullable=False),
        sa.Column("source_law_number", sa.String(24), nullable=False),
        sa.Column("source_law_year", sa.Integer(), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("law_source_url", sa.Text(), nullable=False),
        sa.Column("before_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("after_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("evidence_marker", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("law_slug", "node_id", "source_law_number", "source_law_year", name="uq_change_provenance"),
    )
    op.create_index("ix_law_changes_law_slug", "law_changes", ["law_slug"])
    op.create_index("ix_law_changes_node_id", "law_changes", ["node_id"])

    op.create_table(
        "hydration_jobs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("law_slug", sa.String(96), sa.ForeignKey("laws.slug", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="queued"),
        sa.Column("stage", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("message", sa.String(240), nullable=False, server_default="Aguardando preparação"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_hydration_jobs_law_slug", "hydration_jobs", ["law_slug"])
    op.create_index("ix_hydration_jobs_status", "hydration_jobs", ["status"])


def downgrade() -> None:
    for table, columns in [
        ("hydration_jobs", ["law_slug", "status"]),
        ("law_changes", ["law_slug", "node_id"]),
        ("source_snapshots", ["law_slug", "version_id", "checksum"]),
        ("legal_nodes", ["law_slug", "version_id", "node_id", "parent_node_id", "node_type", "order_index"]),
        ("law_versions", ["law_slug", "checksum", "is_current"]),
        ("laws", ["jurisdiction", "year", "title", "hot", "materialization_status"]),
    ]:
        for column in columns:
            op.drop_index(f"ix_{table}_{column}", table_name=table)
        op.drop_table(table)

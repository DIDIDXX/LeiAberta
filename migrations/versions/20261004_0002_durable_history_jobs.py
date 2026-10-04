"""Persist history discovery, durable stream dispatch and source status honestly."""
from alembic import op
import sqlalchemy as sa

revision = "20261004_0002"
down_revision = "20261004_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("hydration_jobs", sa.Column("job_type", sa.String(24), nullable=False, server_default="hydrate"))
    op.add_column("hydration_jobs", sa.Column("stage_name", sa.String(40), nullable=False, server_default="queued"))
    op.add_column("hydration_jobs", sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True))
    op.add_column("hydration_jobs", sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_hydration_jobs_job_type", "hydration_jobs", ["job_type"])
    op.create_index(
        "uq_active_job_per_law_type", "hydration_jobs", ["law_slug", "job_type"], unique=True,
        postgresql_where=sa.text("status IN ('queued', 'running')"),
        sqlite_where=sa.text("status IN ('queued', 'running')"),
    )
    op.create_table(
        "job_outbox",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("job_id", sa.String(36), sa.ForeignKey("hydration_jobs.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("dispatched_at", sa.DateTime(timezone=True)),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_job_outbox_job_id", "job_outbox", ["job_id"])
    op.create_index("ix_job_outbox_available_at", "job_outbox", ["available_at"])
    op.create_table(
        "history_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("law_slug", sa.String(96), sa.ForeignKey("laws.slug", ondelete="CASCADE"), nullable=False),
        sa.Column("source_id", sa.String(96), nullable=False),
        sa.Column("device_ref", sa.String(240), nullable=False, server_default=""),
        sa.Column("relation", sa.String(120), nullable=False),
        sa.Column("event_label", sa.String(240), nullable=False),
        sa.Column("event_url", sa.Text(), nullable=False),
        sa.Column("signed_at", sa.Date()),
        sa.Column("publication_date", sa.Date()),
        sa.Column("evidence", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(24), nullable=False, server_default="discovered"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("law_slug", "source_id", "device_ref", name="uq_history_event_source_device"),
    )
    op.create_index("ix_history_events_law_slug", "history_events", ["law_slug"])
    if op.get_bind().dialect.name == "postgresql":
        op.alter_column("laws", "status", server_default="Não verificado")
        op.execute(sa.text("UPDATE laws SET materialization_status = 'partial' WHERE materialization_status = 'ready' AND current_version_id IS NOT NULL"))
        op.execute(sa.text("UPDATE laws SET coverage = jsonb_set(coverage::jsonb, '{structured_text}', '\"partial\"'::jsonb)::json WHERE current_version_id IS NOT NULL"))
    # No status source was stored for the seed values; they must not be shown as certified.
    op.execute(sa.text("UPDATE laws SET status = 'Não verificado' WHERE status = 'Em vigor'"))


def downgrade() -> None:
    op.drop_index("ix_history_events_law_slug", table_name="history_events")
    op.drop_table("history_events")
    op.drop_index("ix_job_outbox_available_at", table_name="job_outbox")
    op.drop_index("ix_job_outbox_job_id", table_name="job_outbox")
    op.drop_table("job_outbox")
    op.drop_index("uq_active_job_per_law_type", table_name="hydration_jobs")
    op.drop_index("ix_hydration_jobs_job_type", table_name="hydration_jobs")
    op.drop_column("hydration_jobs", "heartbeat_at")
    op.drop_column("hydration_jobs", "lease_until")
    op.drop_column("hydration_jobs", "stage_name")
    op.drop_column("hydration_jobs", "job_type")
    if op.get_bind().dialect.name == "postgresql":
        op.alter_column("laws", "status", server_default="Em vigor")

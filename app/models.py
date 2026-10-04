from datetime import date, datetime, timezone

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, Integer, LargeBinary, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.db import Base


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


class Law(Base):
    __tablename__ = "laws"

    slug: Mapped[str] = mapped_column(String(96), primary_key=True)
    jurisdiction: Mapped[str] = mapped_column(String(24), default="federal", index=True)
    state_code: Mapped[str | None] = mapped_column(String(2), nullable=True)
    municipality: Mapped[str | None] = mapped_column(String(120), nullable=True)
    law_type: Mapped[str] = mapped_column(String(48))
    number: Mapped[str] = mapped_column(String(96), index=True)
    year: Mapped[int] = mapped_column(Integer, index=True)
    external_source_id: Mapped[str | None] = mapped_column(String(96), unique=True, nullable=True)
    signed_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    title: Mapped[str] = mapped_column(String(300), index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(48), default="Não verificado")
    published_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    aliases: Mapped[list] = mapped_column(JSON, default=list)
    source_name: Mapped[str] = mapped_column(String(120), default="Presidência da República — Planalto")
    source_url: Mapped[str] = mapped_column(Text)
    fetch_url: Mapped[str] = mapped_column(Text)
    hot: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    materialization_status: Mapped[str] = mapped_column(String(24), default="catalog", index=True)
    last_hydrated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    current_version_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    coverage: Mapped[dict] = mapped_column(JSON, default=dict)

    versions: Mapped[list["LawVersion"]] = relationship(back_populates="law", cascade="all, delete-orphan", foreign_keys="LawVersion.law_slug")


class Jurisdiction(Base):
    __tablename__ = "jurisdictions"

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    kind: Mapped[str] = mapped_column(String(24), index=True)
    name: Mapped[str] = mapped_column(String(180), index=True)
    ibge_code: Mapped[str | None] = mapped_column(String(12), unique=True, nullable=True)
    uf: Mapped[str | None] = mapped_column(String(2), index=True, nullable=True)
    parent_id: Mapped[str | None] = mapped_column(ForeignKey("jurisdictions.id"), nullable=True, index=True)
    legislature_eligible: Mapped[bool] = mapped_column(Boolean, default=True)
    territorial_status: Mapped[str] = mapped_column(String(32), default="active")
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, default=dict)
    source_url: Mapped[str] = mapped_column(Text)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class SourceRegistry(Base):
    __tablename__ = "source_registry"

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    jurisdiction_id: Mapped[str | None] = mapped_column(ForeignKey("jurisdictions.id"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(180))
    adapter: Mapped[str] = mapped_column(String(48))
    base_url: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="discovered", index=True)
    scope: Mapped[dict] = mapped_column(JSON, default=dict)
    evidence_url: Mapped[str] = mapped_column(Text)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str] = mapped_column(Text, default="")


class LawVersion(Base):
    __tablename__ = "law_versions"
    __table_args__ = (UniqueConstraint("law_slug", "checksum", "parser_version", name="uq_law_version_checksum_parser"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    law_slug: Mapped[str] = mapped_column(ForeignKey("laws.slug", ondelete="CASCADE"), index=True)
    version_name: Mapped[str] = mapped_column(String(160))
    source_url: Mapped[str] = mapped_column(Text)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    checksum: Mapped[str] = mapped_column(String(64), index=True)
    parser_version: Mapped[str] = mapped_column(String(32), default="1.0")
    is_current: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    article_count: Mapped[int] = mapped_column(Integer, default=0)

    law: Mapped[Law] = relationship(back_populates="versions", foreign_keys=[law_slug])
    nodes: Mapped[list["LegalNode"]] = relationship(back_populates="version", cascade="all, delete-orphan")


class LegalNode(Base):
    __tablename__ = "legal_nodes"
    __table_args__ = (UniqueConstraint("version_id", "node_id", name="uq_legal_node_version_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    law_slug: Mapped[str] = mapped_column(ForeignKey("laws.slug", ondelete="CASCADE"), index=True)
    version_id: Mapped[int] = mapped_column(ForeignKey("law_versions.id", ondelete="CASCADE"), index=True)
    node_id: Mapped[str] = mapped_column(String(160), index=True)
    parent_node_id: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)
    node_type: Mapped[str] = mapped_column(String(24), index=True)
    label: Mapped[str] = mapped_column(String(64))
    text: Mapped[str] = mapped_column(Text)
    source_note: Mapped[str] = mapped_column(Text, default="")
    order_index: Mapped[int] = mapped_column(Integer, index=True)

    version: Mapped[LawVersion] = relationship(back_populates="nodes")


class SourceSnapshot(Base):
    __tablename__ = "source_snapshots"
    __table_args__ = (UniqueConstraint("law_slug", "checksum", name="uq_source_snapshot_checksum"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    law_slug: Mapped[str] = mapped_column(ForeignKey("laws.slug", ondelete="CASCADE"), index=True)
    # A captured official response exists independently of whether parsing
    # succeeds or a parser representation has been published.
    version_id: Mapped[int | None] = mapped_column(ForeignKey("law_versions.id", ondelete="SET NULL"), nullable=True, index=True)
    source_url: Mapped[str] = mapped_column(Text)
    checksum: Mapped[str] = mapped_column(String(64), index=True)
    raw_format: Mapped[str] = mapped_column(String(80), default="text/html; charset=iso-8859-1")
    raw_body: Mapped[bytes] = mapped_column(LargeBinary)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class LawChange(Base):
    __tablename__ = "law_changes"
    __table_args__ = (UniqueConstraint("law_slug", "node_id", "source_law_number", "source_law_year", name="uq_change_provenance"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    law_slug: Mapped[str] = mapped_column(ForeignKey("laws.slug", ondelete="CASCADE"), index=True)
    node_id: Mapped[str] = mapped_column(String(160), index=True)
    change_type: Mapped[str] = mapped_column(String(16), default="ADD")
    summary: Mapped[str] = mapped_column(String(300))
    changed_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    source_law_label: Mapped[str] = mapped_column(String(180))
    source_law_number: Mapped[str] = mapped_column(String(24))
    source_law_year: Mapped[int] = mapped_column(Integer)
    source_url: Mapped[str] = mapped_column(Text)
    law_source_url: Mapped[str] = mapped_column(Text)
    before_text: Mapped[str] = mapped_column(Text, default="")
    after_text: Mapped[str] = mapped_column(Text, default="")
    evidence_marker: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class HistoryEvent(Base):
    """An official relation discovered for a norm; not necessarily a validated text diff."""
    __tablename__ = "history_events"
    __table_args__ = (UniqueConstraint("law_slug", "source_id", "device_ref", name="uq_history_event_source_device"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    law_slug: Mapped[str] = mapped_column(ForeignKey("laws.slug", ondelete="CASCADE"), index=True)
    source_id: Mapped[str] = mapped_column(String(96))
    device_ref: Mapped[str] = mapped_column(String(240), default="")
    relation: Mapped[str] = mapped_column(String(120))
    event_label: Mapped[str] = mapped_column(String(240))
    event_url: Mapped[str] = mapped_column(Text)
    signed_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    publication_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    evidence: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(24), default="discovered")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

    law: Mapped[Law] = relationship()


class HydrationJob(Base):
    __tablename__ = "hydration_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    law_slug: Mapped[str] = mapped_column(ForeignKey("laws.slug", ondelete="CASCADE"), index=True)
    job_type: Mapped[str] = mapped_column(String(24), default="hydrate", index=True)
    status: Mapped[str] = mapped_column(String(20), default="queued", index=True)
    stage: Mapped[int] = mapped_column(Integer, default=0)
    stage_name: Mapped[str] = mapped_column(String(40), default="queued")
    message: Mapped[str] = mapped_column(String(240), default="Aguardando preparação")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)


class JobOutbox(Base):
    __tablename__ = "job_outbox"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("hydration_jobs.id", ondelete="CASCADE"), unique=True, index=True)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, index=True)
    dispatched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


Index(
    "uq_active_job_per_law_type",
    HydrationJob.law_slug,
    HydrationJob.job_type,
    unique=True,
    postgresql_where=HydrationJob.status.in_(["queued", "running"]),
    sqlite_where=HydrationJob.status.in_(["queued", "running"]),
)

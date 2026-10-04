from datetime import date, datetime, timezone

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, LargeBinary, String, Text, UniqueConstraint
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
    number: Mapped[str] = mapped_column(String(24))
    year: Mapped[int] = mapped_column(Integer, index=True)
    title: Mapped[str] = mapped_column(String(300), index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(48), default="Em vigor")
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


class LawVersion(Base):
    __tablename__ = "law_versions"
    __table_args__ = (UniqueConstraint("law_slug", "checksum", name="uq_law_version_checksum"),)

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
    version_id: Mapped[int] = mapped_column(ForeignKey("law_versions.id", ondelete="CASCADE"), index=True)
    source_url: Mapped[str] = mapped_column(Text)
    checksum: Mapped[str] = mapped_column(String(64), index=True)
    raw_format: Mapped[str] = mapped_column(String(32), default="text/html; charset=iso-8859-1")
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


class HydrationJob(Base):
    __tablename__ = "hydration_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    law_slug: Mapped[str] = mapped_column(ForeignKey("laws.slug", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(20), default="queued", index=True)
    stage: Mapped[int] = mapped_column(Integer, default=0)
    message: Mapped[str] = mapped_column(String(240), default="Aguardando preparação")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)

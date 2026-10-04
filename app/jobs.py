from __future__ import annotations

import hashlib
import logging
import os
import re
import threading
import uuid
from datetime import date, datetime, timezone

from sqlalchemy import select

from app.catalog import AMENDING_LAWS
from app.db import SessionLocal
from app.models import HydrationJob, Law, LawChange, LawVersion, LegalNode, SourceSnapshot
from app.sources.planalto import PARSER_VERSION, detect_raw_format, extract_paragraphs, fetch_official_html, parse_legal_nodes, source_note_for_law

logger = logging.getLogger("leiaberta.jobs")
QUEUE_NAME = "leiaberta:hydrate"


def queue_hydration(law: Law) -> HydrationJob:
    session = SessionLocal()
    try:
        stored_law = session.get(Law, law.slug)
        if not stored_law:
            raise ValueError("Norma não encontrada no catálogo.")
        existing = session.scalar(
            select(HydrationJob)
            .where(HydrationJob.law_slug == law.slug, HydrationJob.status.in_(["queued", "running"]))
            .order_by(HydrationJob.created_at.desc())
            .limit(1)
        )
        if existing:
            return existing
        if stored_law.materialization_status == "ready":
            return HydrationJob(id="", law_slug=stored_law.slug, status="succeeded", stage=5, message="Texto e dispositivos disponíveis")
        job = HydrationJob(id=str(uuid.uuid4()), law_slug=law.slug)
        session.add(job)
        stored_law.materialization_status = "preparing"
        session.commit()
        session.refresh(job)
    finally:
        session.close()

    redis_url = os.getenv("REDIS_URL", "")
    if redis_url:
        try:
            from redis import Redis

            Redis.from_url(redis_url, socket_connect_timeout=2, socket_timeout=2).rpush(QUEUE_NAME, job.id)
            return job
        except Exception as exc:  # Redis is optional in local development; Railway config is monitored separately.
            logger.warning("redis_enqueue_failed law_id=%s error=%s", law.slug, str(exc)[:200])

    threading.Thread(target=process_hydration_job, args=(job.id,), daemon=True).start()
    return job


def _update_job(session, job: HydrationJob, *, status: str | None = None, stage: int | None = None,
                message: str | None = None, error: str | None = None) -> None:
    if status is not None:
        job.status = status
    if stage is not None:
        job.stage = stage
    if message is not None:
        job.message = message
    if error is not None:
        job.error = error
    job.updated_at = datetime.now(timezone.utc)
    session.commit()


def _flat(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.casefold())


def _verified_lmp_changes(session, law: Law, version: LawVersion, nodes: list[LegalNode]) -> int:
    """Record additions only when the current official text cites the amending law and repeats in it."""
    created = 0
    by_key = {(number, year): meta for (number, year), meta in AMENDING_LAWS.items()}
    for node in nodes:
        provenance = source_note_for_law(node.source_note)
        if not provenance or provenance not in by_key or node.node_type != "paragraph":
            continue
        amendment = by_key[provenance]
        try:
            amendment_body, _ = fetch_official_html(amendment["fetch_url"])
        except Exception as exc:
            logger.warning("amendment_source_unavailable law_id=%s node=%s error=%s", law.slug, node.node_id, str(exc)[:180])
            continue
        amendment_text = _flat(" ".join(line for line, _ in extract_paragraphs(amendment_body)))
        new_text = _flat(node.text)
        if len(new_text) < 40 or new_text not in amendment_text:
            logger.warning("amendment_text_unverified law_id=%s node=%s source=%s", law.slug, node.node_id, amendment["source_url"])
            continue

        exists = session.scalar(select(LawChange.id).where(
            LawChange.law_slug == law.slug,
            LawChange.node_id == node.node_id,
            LawChange.source_law_number == provenance[0],
            LawChange.source_law_year == provenance[1],
        ).limit(1))
        if exists:
            continue
        label = node.label
        change = LawChange(
            id=str(uuid.uuid4()), law_slug=law.slug, node_id=node.node_id, change_type="ADD",
            summary=f"Acrescentou o {label} ao Art. 19º", changed_at=date.fromisoformat(amendment["changed_at"]),
            source_law_label=amendment["label"], source_law_number=provenance[0], source_law_year=provenance[1],
            source_url=amendment["source_url"], law_source_url=version.source_url, before_text="",
            after_text=node.text, evidence_marker=node.source_note,
        )
        session.add(change)
        created += 1
    return created


def process_hydration_job(job_id: str) -> None:
    session = SessionLocal()
    try:
        job = session.get(HydrationJob, job_id)
        if not job or job.status == "succeeded":
            return
        law = session.get(Law, job.law_slug)
        if not law:
            _update_job(session, job, status="failed", message="Norma não encontrada no catálogo", error="law_missing")
            return

        _update_job(session, job, status="running", stage=1, message="Fonte oficial localizada", error="")
        law.materialization_status = "preparing"
        session.commit()
        logger.info("hydration_started source=%s job=%s jurisdiction=%s law_id=%s", law.source_name, job.id, law.jurisdiction, law.slug)

        _update_job(session, job, stage=2, message="Obtendo texto da fonte oficial")
        body, _fetched_url = fetch_official_html(law.fetch_url)
        checksum = hashlib.sha256(body).hexdigest()

        existing = session.scalar(select(LawVersion).where(LawVersion.law_slug == law.slug, LawVersion.checksum == checksum).limit(1))
        if existing and existing.parser_version == PARSER_VERSION:
            version = existing
            nodes = list(session.scalars(select(LegalNode).where(LegalNode.version_id == version.id).order_by(LegalNode.order_index)))
        else:
            _update_job(session, job, stage=3, message="Estruturando artigos e dispositivos")
            parsed = parse_legal_nodes(body)
            if not parsed:
                raise ValueError("A fonte respondeu, mas nenhum dispositivo jurídico foi reconhecido.")
            session.query(LawVersion).filter(LawVersion.law_slug == law.slug).update({"is_current": False})
            if existing:
                version = existing
                session.query(LegalNode).filter(LegalNode.version_id == version.id).delete(synchronize_session=False)
                version.parser_version = PARSER_VERSION
                version.source_url = law.source_url
                version.is_current = True
                version.article_count = sum(1 for node in parsed if node.node_type == "article")
            else:
                version = LawVersion(
                    law_slug=law.slug, version_name="Texto consolidado consultado", source_url=law.source_url,
                    checksum=checksum, parser_version=PARSER_VERSION, is_current=True,
                    article_count=sum(1 for node in parsed if node.node_type == "article"),
                )
                session.add(version)
                session.flush()
            nodes = [LegalNode(
                law_slug=law.slug, version_id=version.id, node_id=node.node_id, parent_node_id=node.parent_node_id,
                node_type=node.node_type, label=node.label, text=node.text, source_note=node.source_note,
                order_index=node.order_index,
            ) for node in parsed]
            session.add_all(nodes)
            snapshot_exists = session.scalar(select(SourceSnapshot.id).where(
                SourceSnapshot.law_slug == law.slug, SourceSnapshot.checksum == checksum,
            ).limit(1))
            if not snapshot_exists:
                session.add(SourceSnapshot(
                    law_slug=law.slug, version_id=version.id, source_url=law.source_url,
                    checksum=checksum, raw_format=detect_raw_format(body), raw_body=body,
                ))
            session.flush()

        _update_job(session, job, stage=4, message="Conferindo referências de alteração")
        linked_changes = _verified_lmp_changes(session, law, version, nodes) if law.slug == "11340-2006" else 0
        law.current_version_id = version.id
        law.materialization_status = "ready"
        law.last_hydrated_at = datetime.now(timezone.utc)
        law.coverage = {
            "official_source": "available",
            "structured_text": "available",
            "history": "partial" if linked_changes or session.scalar(select(LawChange.id).where(LawChange.law_slug == law.slug).limit(1)) else "not_materialized",
            "attribution": "partial" if linked_changes else "not_identified",
            "authors": "not_available",
            "votes": "not_available",
            "snapshot_checksum": checksum,
        }
        _update_job(session, job, status="succeeded", stage=5, message="Texto e dispositivos disponíveis")
        session.commit()
        logger.info("hydration_finished source=%s job=%s jurisdiction=%s law_id=%s duration_state=success articles=%s changes=%s checksum=%s",
                    law.source_name, job.id, law.jurisdiction, law.slug, version.article_count, linked_changes, checksum)
    except Exception as exc:
        session.rollback()
        job = session.get(HydrationJob, job_id)
        if job:
            job.status = "failed"
            job.message = "A fonte oficial não pôde ser processada desta vez"
            job.error = str(exc)[:1000]
            job.updated_at = datetime.now(timezone.utc)
            law = session.get(Law, job.law_slug)
            if law and law.materialization_status != "ready":
                law.materialization_status = "unavailable"
            session.commit()
            logger.exception("hydration_failed job=%s law_id=%s", job_id, job.law_slug)
    finally:
        session.close()

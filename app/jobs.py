from __future__ import annotations

import hashlib
import logging
import os
import re
import threading
import uuid
from datetime import date, datetime, timedelta, timezone
from sqlalchemy.exc import IntegrityError
from sqlalchemy import and_, or_, update

from sqlalchemy import select

from app.catalog import AMENDING_LAWS
from app.db import SessionLocal
from app.models import HistoryEvent, HydrationJob, JobOutbox, Law, LawChange, LawVersion, LegalNode, SourceSnapshot
from app.sources.planalto import PARSER_VERSION, detect_raw_format, extract_paragraphs, fetch_official_html, parse_legal_nodes, source_note_for_law

logger = logging.getLogger("leiaberta.jobs")
QUEUE_NAME = "leiaberta:hydrate"
QUEUE_GROUP = "leiaberta-workers"
ACTIVE_STATUSES = ["queued", "running"]


def queue_job(law_slug: str, job_type: str, *, refresh: bool = False) -> HydrationJob:
    if job_type not in {"hydrate", "history"}:
        raise ValueError("Tipo de job desconhecido.")
    session = SessionLocal()
    try:
        stored_law = session.get(Law, law_slug)
        if not stored_law:
            raise ValueError("Norma não encontrada no catálogo.")
        existing = session.scalar(
            select(HydrationJob)
            .where(HydrationJob.law_slug == law_slug, HydrationJob.job_type == job_type, HydrationJob.status.in_(ACTIVE_STATUSES))
            .order_by(HydrationJob.created_at.desc())
            .limit(1)
        )
        if existing:
            return existing
        if job_type == "hydrate" and stored_law.materialization_status == "ready" and not refresh:
            done = session.scalar(select(HydrationJob).where(HydrationJob.law_slug == law_slug, HydrationJob.job_type == job_type, HydrationJob.status == "succeeded").order_by(HydrationJob.updated_at.desc()).limit(1))
            if done:
                return done
        job = HydrationJob(id=str(uuid.uuid4()), law_slug=law_slug, job_type=job_type,
                           stage_name="queued", message="Aguardando worker")
        session.add(job)
        session.add(JobOutbox(job_id=job.id))
        if job_type == "hydrate" and stored_law.materialization_status != "ready":
            stored_law.materialization_status = "preparing"
        if job_type == "history":
            coverage = dict(stored_law.coverage or {})
            if coverage.get("history") in {None, "not_materialized", "not_requested", "unavailable", "failed"}:
                coverage["history"] = "queued"
            stored_law.coverage = coverage
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            active = session.scalar(select(HydrationJob).where(
                HydrationJob.law_slug == law_slug, HydrationJob.job_type == job_type,
                HydrationJob.status.in_(ACTIVE_STATUSES)).order_by(HydrationJob.created_at.desc()).limit(1))
            if active:
                return active
            raise
        session.refresh(job)
        try:
            dispatch_outbox()
        except Exception as exc:
            logger.warning("job_dispatch_deferred job=%s error=%s", job.id, str(exc)[:160])
        if not os.getenv("REDIS_URL") and os.getenv("APP_ENV") != "production" and os.getenv("LOCAL_INLINE_JOBS") == "1":
            threading.Thread(target=process_hydration_job, args=(job.id,), daemon=True).start()
        return job
    finally:
        session.close()


def queue_hydration(law: Law, *, refresh: bool = False) -> HydrationJob:
    return queue_job(law.slug, "hydrate", refresh=refresh)


def queue_history(law: Law) -> HydrationJob:
    return queue_job(law.slug, "history")


def dispatch_outbox(limit: int = 100) -> int:
    redis_url = os.getenv("REDIS_URL", "")
    if not redis_url:
        return 0
    from redis import Redis
    redis = Redis.from_url(redis_url, decode_responses=True, socket_connect_timeout=2, socket_timeout=2)
    session = SessionLocal()
    dispatched = 0
    try:
        events = list(session.scalars(select(JobOutbox).where(JobOutbox.dispatched_at.is_(None), JobOutbox.available_at <= datetime.now(timezone.utc)).order_by(JobOutbox.id).limit(limit).with_for_update(skip_locked=True)))
        for event in events:
            redis.xadd(QUEUE_NAME, {"job_id": event.job_id})
            event.dispatched_at = datetime.now(timezone.utc)
            event.attempts += 1
            event.last_error = ""
            dispatched += 1
        session.commit()
        return dispatched
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _update_job(session, job: HydrationJob, *, status: str | None = None, stage: int | None = None,
                message: str | None = None, error: str | None = None) -> None:
    if status is not None:
        job.status = status
    if stage is not None:
        job.stage = stage
        job.stage_name = {0: "queued", 1: "source", 2: "fetch", 3: "parse", 4: "validate", 5: "complete"}.get(stage, "processing")
    if message is not None:
        job.message = message
    if error is not None:
        job.error = error
    if status in {"succeeded", "failed", "cancelled"}:
        job.lease_until = None
    job.updated_at = datetime.now(timezone.utc)
    session.commit()


def _process_history_job(job_id: str) -> None:
    from app.sources.senado import fetch_norm_xml, parse_relation_xml

    session = SessionLocal()
    try:
        job = session.get(HydrationJob, job_id)
        law = session.get(Law, job.law_slug) if job else None
        if not job or not law:
            raise ValueError("Job ou norma não encontrados.")
        _update_job(session, job, stage=1, message="Consultando relações normativas do Senado")
        body, list_url = fetch_norm_xml(law.law_type, law.number, law.year)
        relations = parse_relation_xml(body, expected_number=law.number)
        current_version = session.get(LawVersion, law.current_version_id) if law.current_version_id else None
        checksum = hashlib.sha256(body).hexdigest()
        if current_version and not session.scalar(select(SourceSnapshot.id).where(SourceSnapshot.law_slug == law.slug, SourceSnapshot.checksum == checksum).limit(1)):
            session.add(SourceSnapshot(law_slug=law.slug, version_id=current_version.id, source_url=list_url,
                                       checksum=checksum, raw_format="application/xml; charset=utf-8", raw_body=body))
        _update_job(session, job, stage=2, message=f"Conferindo {len(relations)} referências oficiais")
        created = 0
        for relation in relations:
            event = HistoryEvent(
                id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"senado:{law.slug}:{relation.source_id}:{relation.device_ref}")),
                law_slug=law.slug, source_id=relation.source_id, device_ref=relation.device_ref,
                relation=relation.relation, event_label=relation.event_label,
                event_url=f"https://legis.senado.leg.br/dadosabertos/legislacao/{relation.source_id}",
                signed_at=relation.signed_at, publication_date=relation.publication_date,
                evidence=relation.evidence, status="discovered",
            )
            exists = session.scalar(select(HistoryEvent.id).where(
                HistoryEvent.law_slug == law.slug, HistoryEvent.source_id == relation.source_id,
                HistoryEvent.device_ref == relation.device_ref).limit(1))
            if not exists:
                session.add(event)
                created += 1
        coverage = dict(law.coverage or {})
        # The Senate relations identify candidate events, but do not prove each historical text or legal-effective date.
        coverage["history"] = "partial"
        coverage["history_source"] = "senado"
        coverage["history_checked_at"] = datetime.now(timezone.utc).isoformat()
        coverage["history_relation_count"] = len(relations)
        coverage["history_events_pending_text"] = len(relations)
        law.coverage = coverage
        job.status = "succeeded"
        job.stage = 5
        job.stage_name = "discovered"
        job.message = f"{len(relations)} referências oficiais localizadas; redações anteriores ainda precisam ser conferidas"
        job.error = ""
        job.lease_until = None
        job.updated_at = datetime.now(timezone.utc)
        session.commit()
        logger.info("history_relations_discovered law_id=%s found=%s added=%s", law.slug, len(relations), created)
    finally:
        session.close()


def process_hydration_job(job_id: str) -> bool:
    """Claim persisted work; stream delivery is at-least-once and effects are idempotent."""
    session = SessionLocal()
    now = datetime.now(timezone.utc)
    try:
        job = session.get(HydrationJob, job_id)
        if not job or job.status in {"succeeded", "failed", "cancelled"}:
            return False
        claimable = job.status == "queued" or (job.status == "running" and (job.lease_until is None or job.lease_until <= now))
        if not claimable:
            return False
        claimed = session.execute(update(HydrationJob).where(
            HydrationJob.id == job_id,
            or_(HydrationJob.status == "queued", and_(HydrationJob.status == "running", or_(HydrationJob.lease_until.is_(None), HydrationJob.lease_until <= now))),
        ).values(status="running", stage_name="claimed", lease_until=now + timedelta(minutes=5),
                 heartbeat_at=now, attempts=HydrationJob.attempts + 1, updated_at=now))
        if not claimed.rowcount:
            session.rollback()
            return False
        job_type = job.job_type
        session.commit()
    finally:
        session.close()

    try:
        if job_type == "history":
            _process_history_job(job_id)
        else:
            _process_hydration_job_unchecked(job_id)
        return True
    except Exception as exc:
        retry_session = SessionLocal()
        try:
            failed = retry_session.get(HydrationJob, job_id)
            if not failed:
                return False
            failed.error = str(exc)[:1000]
            failed.updated_at = datetime.now(timezone.utc)
            failed.lease_until = None
            outbox = retry_session.scalar(select(JobOutbox).where(JobOutbox.job_id == job_id).limit(1))
            if failed.attempts < 5 and outbox:
                delay = min(3600, 15 * (2 ** max(0, failed.attempts - 1)))
                failed.status = "queued"
                failed.stage_name = "retry_wait"
                failed.message = f"Fonte temporariamente indisponível; nova tentativa em aproximadamente {delay} s"
                outbox.available_at = datetime.now(timezone.utc) + timedelta(seconds=delay)
                outbox.dispatched_at = None
                outbox.last_error = failed.error
            else:
                failed.status = "failed"
                failed.stage_name = "failed"
                failed.message = "O processamento falhou após novas tentativas"
                law = retry_session.get(Law, failed.law_slug)
                if law:
                    if failed.job_type == "history":
                        coverage = dict(law.coverage or {})
                        coverage["history"] = "unavailable" if coverage.get("history") in {None, "queued"} else "partial"
                        coverage["history_error"] = failed.error[:500]
                        law.coverage = coverage
                    elif not law.current_version_id:
                        law.materialization_status = "unavailable"
            retry_session.commit()
            logger.exception("job_attempt_failed job=%s type=%s", job_id, job_type)
        finally:
            retry_session.close()
        return False


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


def _process_hydration_job_unchecked(job_id: str) -> None:
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
        # Parsing succeeded, but no independent whole-document completeness audit exists yet.
        law.materialization_status = "partial"
        law.last_hydrated_at = datetime.now(timezone.utc)
        law.coverage = {
            "official_source": "available",
            "structured_text": "partial",
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
    except Exception:
        session.rollback()
        logger.exception("hydration_failed job=%s", job_id)
        raise
    finally:
        session.close()

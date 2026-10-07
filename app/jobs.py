from __future__ import annotations

import hashlib
import logging
import os
import re
import threading
import uuid
from datetime import date, datetime, timedelta, timezone
from sqlalchemy.exc import IntegrityError
from sqlalchemy import and_, func, or_, update

from sqlalchemy import select

from app.audit import audit_archived_document
from app.catalog import AMENDING_LAWS
from app.db import SessionLocal
from app.models import HistoryEvent, HydrationJob, JobOutbox, Law, LawChange, LawVersion, LegalNode, SenateProceeding, SourceSnapshot
from app.storage.source_snapshots import archive_snapshot_object
from app.sources.normas import SourceDocumentUnavailable
from app.sources.planalto import PARSER_VERSION, ParsedNode, detect_raw_format, extract_paragraphs, fetch_official_html, parse_legal_nodes, source_note_for_law

logger = logging.getLogger("leiaberta.jobs")
QUEUE_NAME = "leiaberta:hydrate"
QUEUE_GROUP = "leiaberta-workers"
ACTIVE_STATUSES = ["queued", "running"]
MAX_INTERACTIVE_JOB_BATCH = 24
BACKGROUND_BACKFILL_MODES = {"off", "hot", "continuous"}
BACKGROUND_BACKFILL_MARKER = "[background-backfill] "
INTERACTIVE_JOB_MARKER = "[interactive-job] "
LEGACY_BACKFILL_MESSAGES = (
    "Aguardando captura do texto legislativo",
    "Aguardando captura integral da fonte oficial",
    "Aguardando varredura histórica em lote",
)
INTERACTIVE_JOB_MESSAGES = ("Aguardando worker", "Aguardando fila de processamento")
_SUBNATIONAL_BACKFILL_CURSORS: dict[str, str] = {}
_SUBNATIONAL_BACKFILL_SOURCE_CURSOR: str | None = None
_HISTORY_BACKFILL_CURSORS: dict[str, str] = {}
_HISTORY_BACKFILL_SOURCE_CURSOR: str | None = None
_HISTORY_BACKFILL_EXHAUSTED: set[str] = set()
_HISTORY_BACKFILL_RESCAN_AT: datetime | None = None


def background_backfill_mode(value: str | None = None) -> str:
    """Read the worker's bulk-work policy; the safe default pauses bulk work."""
    mode = (value if value is not None else os.getenv("BACKGROUND_BACKFILL_MODE", "off")).strip().lower()
    if mode not in BACKGROUND_BACKFILL_MODES:
        raise ValueError("BACKGROUND_BACKFILL_MODE must be off, hot, or continuous")
    return mode


def _tag_backfill_message(message: str) -> str:
    return message if message.startswith(BACKGROUND_BACKFILL_MARKER) else BACKGROUND_BACKFILL_MARKER + message


def _backfill_message(message: str | None) -> bool:
    return bool(message and (message.startswith(BACKGROUND_BACKFILL_MARKER)
                             or message in LEGACY_BACKFILL_MESSAGES))


def _tag_interactive_message(message: str) -> str:
    return message if message.startswith(INTERACTIVE_JOB_MARKER) else INTERACTIVE_JOB_MARKER + message


def _job_message(job: HydrationJob, message: str) -> str:
    """Retain durable work-class markers as progress text changes or retries."""
    if _backfill_message(job.message) or job.message in LEGACY_BACKFILL_MESSAGES:
        return _tag_backfill_message(message)
    if job.message.startswith(INTERACTIVE_JOB_MARKER):
        return _tag_interactive_message(message)
    return message


def public_job_message(job: HydrationJob) -> str:
    """Hide internal queue markers from API clients and the reader UI."""
    for marker in (BACKGROUND_BACKFILL_MARKER, INTERACTIVE_JOB_MARKER):
        if job.message.startswith(marker):
            return job.message[len(marker):]
    return job.message


def _backfill_mode_allows(mode: str, *, hot: bool) -> bool:
    return mode == "continuous" or (mode == "hot" and hot)


def should_process_job(job_id: str, *, mode: str | None = None) -> bool:
    """Only process known interactive or mode-eligible bulk jobs; defer ambiguity."""
    policy = background_backfill_mode(mode)
    if policy == "continuous":
        return True
    with SessionLocal() as session:
        row = session.execute(
            select(HydrationJob.status, HydrationJob.message, Law.hot)
            .join(Law, Law.slug == HydrationJob.law_slug)
            .where(HydrationJob.id == job_id)
        ).first()
    if row is None:
        return True
    status, message, law_is_hot = row
    if status in {"succeeded", "failed", "cancelled"}:
        # The process function's durable terminal guard returns False; ACKing
        # that stale stream delivery cannot erase retryable or queued work.
        return True
    if message in INTERACTIVE_JOB_MESSAGES or message.startswith(INTERACTIVE_JOB_MARKER):
        return True
    if _backfill_message(message):
        return _backfill_mode_allows(policy, hot=bool(law_is_hot))
    return False


def _bounded_backfill_limit(session, requested: int, *, job_type: str, source_names: tuple[str, ...],
                            env_name: str, default: int) -> tuple[int, int, int]:
    """Bound background work to a queue depth the worker can actually drain."""
    try:
        active_limit = int(os.getenv(env_name, str(default)))
    except ValueError as exc:
        raise ValueError(f"{env_name} must be an integer") from exc
    if not 0 <= active_limit <= 10_000:
        raise ValueError(f"{env_name} must be between 0 and 10000")
    active_jobs = int(session.scalar(
        select(func.count()).select_from(HydrationJob)
        .join(Law, Law.slug == HydrationJob.law_slug)
        .where(HydrationJob.job_type == job_type,
               HydrationJob.status.in_(ACTIVE_STATUSES),
               Law.source_name.in_(source_names))
    ) or 0)
    return min(requested, max(0, active_limit - active_jobs)), active_jobs, active_limit


def queue_job(law_slug: str, job_type: str, *, refresh: bool = False, priority: bool = False) -> HydrationJob:
    if job_type not in {"hydrate", "history", "provenance"}:
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
            if priority and existing.status == "queued" and existing.message != "Aguardando worker":
                existing.message = _tag_interactive_message("Aguardando worker")
                session.commit()
                session.refresh(existing)
            return existing
        if job_type == "hydrate" and stored_law.materialization_status == "ready" and not refresh:
            done = session.scalar(select(HydrationJob).where(HydrationJob.law_slug == law_slug, HydrationJob.job_type == job_type, HydrationJob.status == "succeeded").order_by(HydrationJob.updated_at.desc()).limit(1))
            if done:
                return done
        if job_type == "provenance" and not refresh:
            dossier = session.get(SenateProceeding, law_slug)
            if dossier and dossier.status in {"complete", "partial", "no_process"}:
                done = session.scalar(select(HydrationJob).where(
                    HydrationJob.law_slug == law_slug, HydrationJob.job_type == job_type,
                    HydrationJob.status == "succeeded",
                ).order_by(HydrationJob.updated_at.desc()).limit(1))
                if done:
                    return done
        initial_message = "Aguardando worker" if priority else "Aguardando fila de processamento"
        if priority:
            initial_message = _tag_interactive_message(initial_message)
        job = HydrationJob(id=str(uuid.uuid4()), law_slug=law_slug, job_type=job_type,
                           stage_name="queued", message=initial_message)
        session.add(job)
        session.add(JobOutbox(job_id=job.id))
        if job_type == "hydrate" and not stored_law.current_version_id:
            stored_law.materialization_status = "preparing"
        if job_type == "history":
            coverage = dict(stored_law.coverage or {})
            if coverage.get("history") in {None, "not_materialized", "not_requested", "unavailable", "failed"}:
                coverage["history"] = "queued"
            stored_law.coverage = coverage
        if job_type == "provenance":
            coverage = dict(stored_law.coverage or {})
            coverage["senate_provenance"] = "queued"
            coverage.pop("senate_provenance_error", None)
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
    return queue_job(law.slug, "hydrate", refresh=refresh, priority=True)


def queue_senado_text_batch(*, limit: int = 100, mode: str | None = None) -> dict:
    """Queue one bounded part of the Senate catalog for text retrieval."""
    if not 1 <= limit <= 500:
        raise ValueError("O lote de textos deve conter de 1 a 500 normas.")
    policy = background_backfill_mode(mode)
    if policy == "off":
        return {"queued_count": 0, "limit": 0, "requested_limit": limit,
                "capacity_reached": False, "paused": True, "jobs": []}
    session = SessionLocal()
    jobs: list[dict] = []
    try:
        batch_limit, active_jobs, active_limit = _bounded_backfill_limit(
            session, limit, job_type="hydrate",
            source_names=("Senado Federal — Dados Abertos Legislativos",),
            env_name="SENADO_TEXT_BACKFILL_MAX_ACTIVE_JOBS", default=600,
        )
        if batch_limit == 0:
            return {"queued_count": 0, "limit": 0, "requested_limit": limit,
                    "active_jobs": active_jobs, "active_job_limit": active_limit,
                    "capacity_reached": True, "jobs": jobs}
        latest_hydration_id = (
            select(HydrationJob.id)
            .where(HydrationJob.law_slug == Law.slug, HydrationJob.job_type == "hydrate")
            .order_by(HydrationJob.created_at.desc(), HydrationJob.id.desc())
            .limit(1)
            .correlate(Law)
            .scalar_subquery()
        )
        latest_hydration_status = select(HydrationJob.status).where(
            HydrationJob.id == latest_hydration_id
        ).scalar_subquery()
        latest_hydration_error = select(HydrationJob.error).where(
            HydrationJob.id == latest_hydration_id
        ).scalar_subquery()
        # These were permanent failures in the previous release, not source
        # limitations. Retry each once after the parser/URN fixes; if the new
        # attempt fails for another reason, it no longer matches this list.
        repaired_errors = (
            "A fonte respondeu, mas nenhum dispositivo jurídico foi reconhecido.",
            "O registro não contém uma URN federal de legislação reconhecida.",
            "Os metadados do Normas.leg.br não correspondem à URN solicitada.",
            "O registro oficial não possui uma representação HTML de texto integral.",
            "A identidade da norma não contém número reconhecível.",
        )
        no_prior_job = latest_hydration_id.is_(None)
        retry_after_repair = and_(
            latest_hydration_status == "failed",
            latest_hydration_error.in_(repaired_errors),
        )
        laws = list(session.scalars(
            select(Law)
            .where(
                Law.jurisdiction == "federal",
                Law.source_name == "Senado Federal — Dados Abertos Legislativos",
                Law.current_version_id.is_(None),
                *((Law.hot.is_(True),) if policy == "hot" else ()),
                or_(no_prior_job, retry_after_repair),
            )
            .order_by(Law.slug)
            .limit(batch_limit)
        ))
        now = datetime.now(timezone.utc)
        for law in laws:
            job = HydrationJob(
                id=str(uuid.uuid4()), law_slug=law.slug, job_type="hydrate", status="queued",
                stage_name="queued", message=_tag_backfill_message("Aguardando captura do texto legislativo"),
                created_at=now, updated_at=now,
            )
            law.materialization_status = "preparing"
            session.add(job)
            session.add(JobOutbox(job_id=job.id, created_at=now, available_at=now))
            jobs.append({"slug": law.slug, "job_id": job.id})
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
    if jobs:
        try:
            dispatch_outbox(mode=policy)
        except Exception as exc:
            logger.warning("senado_text_batch_dispatch_deferred count=%s error=%s", len(jobs), str(exc)[:160])
    return {"queued_count": len(jobs), "limit": batch_limit, "requested_limit": limit,
            "active_jobs": active_jobs, "active_job_limit": active_limit,
            "capacity_reached": False, "jobs": jobs}


def queue_subnational_text_batch(*, limit: int = 100, mode: str | None = None) -> dict:
    """Backfill source-published texts from each connected subnational catalog."""
    global _SUBNATIONAL_BACKFILL_SOURCE_CURSOR
    if not 1 <= limit <= 500:
        raise ValueError("O lote de textos subnacionais deve conter de 1 a 500 normas.")
    policy = background_backfill_mode(mode)
    if policy == "off":
        return {"queued_count": 0, "limit": 0, "requested_limit": limit,
                "capacity_reached": False, "paused": True, "queued_by_source": {}, "jobs": []}
    from app.catalog_sync.sapl import SAPL_INSTANCES

    supported_source_names = (
        "Assembleia Legislativa do Estado de São Paulo — ALESP",
        "Sistema Integrado de Normas Jurídicas do Distrito Federal — SINJ-DF",
        *(instance.source_name for instance in SAPL_INSTANCES),
    )
    session = SessionLocal()
    jobs: list[dict] = []
    queued_by_source: dict[str, int] = {}
    try:
        available_sources = set(session.scalars(
            select(Law.source_name).where(Law.source_name.in_(supported_source_names)).distinct()
        ))
        source_names = tuple(sorted(name for name in supported_source_names if name in available_sources))
        batch_limit, active_jobs, active_limit = _bounded_backfill_limit(
            session, limit, job_type="hydrate", source_names=source_names,
            env_name="SUBNATIONAL_TEXT_BACKFILL_MAX_ACTIVE_JOBS", default=400,
        )
        if batch_limit == 0:
            return {"queued_count": 0, "limit": 0, "requested_limit": limit,
                    "active_jobs": active_jobs, "active_job_limit": active_limit,
                    "capacity_reached": True, "queued_by_source": {}, "jobs": jobs}
        queued_counts = {name: 0 for name in source_names}
        now = datetime.now(timezone.utc)
        if source_names and _SUBNATIONAL_BACKFILL_SOURCE_CURSOR in source_names:
            start = (source_names.index(_SUBNATIONAL_BACKFILL_SOURCE_CURSOR) + 1) % len(source_names)
            source_names = source_names[start:] + source_names[:start]
        remaining = batch_limit
        for source_index, source_name in enumerate(source_names):
            if remaining < 1:
                break
            sources_left = len(source_names) - source_index
            # Spread work evenly when there are fewer sources than slots. If
            # there are more sources than slots, visit each with one job and
            # rotate the first source on the next batch so none is starved.
            source_quota = min(remaining, max(1, (remaining + sources_left - 1) // sources_left))
            _SUBNATIONAL_BACKFILL_SOURCE_CURSOR = source_name
            cursor = _SUBNATIONAL_BACKFILL_CURSORS.get(source_name, "")
            scan_limit = max(500, source_quota * 20)
            statement = select(Law).where(
                Law.source_name == source_name,
                Law.current_version_id.is_(None),
                Law.materialization_status.in_(["catalog", "retryable"]),
                Law.slug > cursor,
                *((Law.hot.is_(True),) if policy == "hot" else ()),
            ).order_by(Law.slug).limit(scan_limit)
            candidates = list(session.scalars(statement))
            if not candidates and cursor:
                cursor = ""
                candidates = list(session.scalars(select(Law).where(
                    Law.source_name == source_name, Law.current_version_id.is_(None),
                    Law.materialization_status.in_(["catalog", "retryable"]),
                    Law.slug > cursor,
                    *((Law.hot.is_(True),) if policy == "hot" else ()),
                ).order_by(Law.slug).limit(scan_limit)))
            selected = []
            last_scanned = cursor
            for law in candidates:
                last_scanned = law.slug
                coverage = dict(law.coverage or {})
                if source_name == "Sistema Integrado de Normas Jurídicas do Distrito Federal — SINJ-DF":
                    has_text = bool(coverage.get("text_attachment_types"))
                else:
                    has_text = coverage.get("text_url_in_catalog") is True
                if not has_text:
                    continue
                retry_after = coverage.get("text_source_retry_after")
                if coverage.get("text_source_status") == "retryable" and retry_after:
                    try:
                        retry_at = datetime.fromisoformat(str(retry_after).replace("Z", "+00:00"))
                        if retry_at.tzinfo is None:
                            retry_at = retry_at.replace(tzinfo=timezone.utc)
                        if retry_at > now:
                            continue
                    except ValueError:
                        pass
                selected.append(law)
                if len(selected) >= source_quota:
                    break
            _SUBNATIONAL_BACKFILL_CURSORS[source_name] = last_scanned
            for law in selected:
                job = HydrationJob(
                    id=str(uuid.uuid4()), law_slug=law.slug, job_type="hydrate", status="queued",
                    stage_name="queued", message=_tag_backfill_message("Aguardando captura integral da fonte oficial"),
                    created_at=now, updated_at=now,
                )
                law.materialization_status = "preparing"
                session.add(job)
                session.add(JobOutbox(job_id=job.id, created_at=now, available_at=now))
                jobs.append({"slug": law.slug, "job_id": job.id, "source": source_name})
                queued_counts[source_name] += 1
                remaining -= 1
        queued_by_source = {name: count for name, count in queued_counts.items() if count}
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
    if jobs:
        try:
            dispatch_outbox(mode=policy)
        except Exception as exc:
            logger.warning("subnational_text_batch_dispatch_deferred count=%s error=%s", len(jobs), str(exc)[:160])
    return {"queued_count": len(jobs), "limit": batch_limit, "requested_limit": limit,
            "active_jobs": active_jobs, "active_job_limit": active_limit,
            "capacity_reached": False, "queued_by_source": queued_by_source, "jobs": jobs}


def queue_official_history_batch(*, limit: int = 500, mode: str | None = None) -> dict:
    """Queue one fair, resumable batch across every connected history adapter."""
    global _HISTORY_BACKFILL_SOURCE_CURSOR, _HISTORY_BACKFILL_RESCAN_AT
    if not 1 <= limit <= 500:
        raise ValueError("O lote de históricos deve conter de 1 a 500 normas.")
    policy = background_backfill_mode(mode)
    if policy == "off":
        return {"queued_count": 0, "limit": 0, "requested_limit": limit,
                "capacity_reached": False, "paused": True, "queued_by_source": {}, "jobs": []}
    from app.catalog_sync.sapl import SAPL_INSTANCES
    from app.sources.senado import TYPE_CODES

    supported_source_names = (
        "Presidência da República — Planalto",
        "Senado Federal — Dados Abertos Legislativos",
        "Assembleia Legislativa do Estado de São Paulo — ALESP",
        "Sistema Integrado de Normas Jurídicas do Distrito Federal — SINJ-DF",
        *(instance.source_name for instance in SAPL_INSTANCES),
    )
    now = datetime.now(timezone.utc)
    if _HISTORY_BACKFILL_RESCAN_AT is None or now >= _HISTORY_BACKFILL_RESCAN_AT:
        _HISTORY_BACKFILL_EXHAUSTED.clear()
        _HISTORY_BACKFILL_RESCAN_AT = now + timedelta(hours=1)

    session = SessionLocal()
    jobs: list[dict] = []
    queued_by_source: dict[str, int] = {}
    try:
        available_sources = set(session.scalars(
            select(Law.source_name).where(Law.source_name.in_(supported_source_names)).distinct()
        ))
        source_names = tuple(sorted(
            name for name in supported_source_names
            if name in available_sources and name not in _HISTORY_BACKFILL_EXHAUSTED
        ))
        batch_limit, active_jobs, active_limit = _bounded_backfill_limit(
            session, limit, job_type="history", source_names=source_names,
            env_name="HISTORY_BACKFILL_MAX_ACTIVE_JOBS", default=400,
        )
        if batch_limit == 0:
            return {"queued_count": 0, "limit": 0, "requested_limit": limit,
                    "active_jobs": active_jobs, "active_job_limit": active_limit,
                    "capacity_reached": True, "queued_by_source": {}, "jobs": jobs}
        if source_names and _HISTORY_BACKFILL_SOURCE_CURSOR in source_names:
            start = (source_names.index(_HISTORY_BACKFILL_SOURCE_CURSOR) + 1) % len(source_names)
            source_names = source_names[start:] + source_names[:start]

        remaining = batch_limit
        for source_index, source_name in enumerate(source_names):
            if remaining < 1:
                break
            sources_left = len(source_names) - source_index
            source_quota = min(remaining, max(1, (remaining + sources_left - 1) // sources_left))
            _HISTORY_BACKFILL_SOURCE_CURSOR = source_name
            cursor = _HISTORY_BACKFILL_CURSORS.get(source_name, "")
            scan_limit = min(2_000, max(20, source_quota * 20))
            statement = select(Law).where(
                Law.source_name == source_name,
                Law.slug > cursor,
                *((Law.hot.is_(True),) if policy == "hot" else ()),
            ).order_by(Law.slug).limit(scan_limit)
            candidates = list(session.scalars(statement))
            if not candidates and cursor:
                cursor = ""
                candidates = list(session.scalars(select(Law).where(
                    Law.source_name == source_name,
                    Law.slug > cursor,
                    *((Law.hot.is_(True),) if policy == "hot" else ()),
                ).order_by(Law.slug).limit(scan_limit)))
            if not candidates:
                _HISTORY_BACKFILL_EXHAUSTED.add(source_name)
                _HISTORY_BACKFILL_CURSORS[source_name] = ""
                continue

            candidate_slugs = [law.slug for law in candidates]
            active_slugs = set(session.scalars(select(HydrationJob.law_slug).where(
                HydrationJob.law_slug.in_(candidate_slugs),
                HydrationJob.job_type == "history",
                HydrationJob.status.in_(ACTIVE_STATUSES),
            )))
            selected = []
            last_scanned = cursor
            for law in candidates:
                last_scanned = law.slug
                coverage = dict(law.coverage or {})
                if coverage.get("history") in {"partial", "complete", "unavailable"}:
                    continue
                if law.slug in active_slugs:
                    continue
                if (source_name == "Senado Federal — Dados Abertos Legislativos"
                        and law.law_type not in TYPE_CODES):
                    continue
                selected.append(law)
                if len(selected) >= source_quota:
                    break

            _HISTORY_BACKFILL_CURSORS[source_name] = last_scanned
            for law in selected:
                coverage = dict(law.coverage or {})
                coverage["history"] = "queued"
                coverage.pop("history_error", None)
                law.coverage = coverage
                job = HydrationJob(
                    id=str(uuid.uuid4()), law_slug=law.slug, job_type="history", status="queued",
                    stage_name="queued", message=_tag_backfill_message("Aguardando varredura histórica em lote"),
                    created_at=now, updated_at=now,
                )
                session.add(job)
                session.add(JobOutbox(job_id=job.id, created_at=now, available_at=now))
                jobs.append({"slug": law.slug, "job_id": job.id, "source": source_name})
                queued_by_source[source_name] = queued_by_source.get(source_name, 0) + 1
                remaining -= 1

            if len(candidates) < scan_limit and len(selected) < source_quota:
                if cursor:
                    # Wrap on the next visit so new records inserted during a
                    # long source sync are included without a full-table scan.
                    _HISTORY_BACKFILL_CURSORS[source_name] = ""
                elif not selected:
                    _HISTORY_BACKFILL_EXHAUSTED.add(source_name)

        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
    if jobs:
        try:
            dispatch_outbox(mode=policy)
        except Exception as exc:
            logger.warning("official_history_batch_dispatch_deferred count=%s error=%s", len(jobs), str(exc)[:160])
    return {"queued_count": len(jobs), "limit": batch_limit, "requested_limit": limit,
            "active_jobs": active_jobs, "active_job_limit": active_limit,
            "capacity_reached": False, "queued_by_source": queued_by_source, "jobs": jobs}


def queue_history(law: Law) -> HydrationJob:
    return queue_job(law.slug, "history", priority=True)


def queue_provenance(law: Law, *, refresh: bool = False) -> HydrationJob:
    return queue_job(law.slug, "provenance", refresh=refresh, priority=True)


def queued_interactive_job_ids(*, limit: int = 4) -> list[str]:
    """Return queued user requests so bulk backfills cannot leave them waiting behind the backlog."""
    if not 1 <= limit <= MAX_INTERACTIVE_JOB_BATCH:
        raise ValueError(f"A consulta prioritária aceita de 1 a {MAX_INTERACTIVE_JOB_BATCH} jobs.")
    with SessionLocal() as session:
        return list(session.scalars(
            select(HydrationJob.id)
            .where(
                HydrationJob.status == "queued",
                HydrationJob.stage_name == "queued",
                or_(
                    and_(HydrationJob.job_type == "history", HydrationJob.message == "Aguardando worker"),
                    and_(HydrationJob.job_type == "provenance", HydrationJob.message == "Aguardando worker"),
                    and_(HydrationJob.job_type == "hydrate", HydrationJob.message == "Aguardando worker"),
                    HydrationJob.message.like(f"{INTERACTIVE_JOB_MARKER}Aguardando worker"),
                ),
            )
            .order_by(HydrationJob.created_at, HydrationJob.id)
            .limit(limit)
        ))


def archive_source_document(law_slug: str, source_url: str, checksum: str, raw_format: str,
                           raw_body: bytes, version_id: int | None = None) -> int:
    """Durably archive official bytes before parsing or relation extraction starts."""
    session = SessionLocal()
    try:
        snapshot = session.scalar(select(SourceSnapshot).where(
            SourceSnapshot.law_slug == law_slug, SourceSnapshot.checksum == checksum,
        ).limit(1))
        if snapshot:
            if snapshot.version_id is None and version_id is not None:
                snapshot.version_id = version_id
            if not snapshot.object_key:
                try:
                    object_ref = archive_snapshot_object(snapshot.raw_body, snapshot.checksum, snapshot.raw_format)
                except Exception as exc:
                    logger.warning("source_snapshot_object_write_failed id=%s error_type=%s; retaining database copy",
                                   snapshot.id, type(exc).__name__)
                    object_ref = None
                if object_ref:
                    snapshot.storage_backend = object_ref.backend
                    snapshot.object_key = object_ref.object_key
                    snapshot.size_bytes = object_ref.size_bytes
            session.commit()
            return snapshot.id
        try:
            object_ref = archive_snapshot_object(raw_body, checksum, raw_format)
        except Exception as exc:
            # The retained PostgreSQL copy remains the system of record during
            # rollout; an unavailable object store must not drop source bytes.
            logger.warning("source_snapshot_object_write_failed law=%s error_type=%s; retaining database copy",
                           law_slug, type(exc).__name__)
            object_ref = None
        snapshot = SourceSnapshot(
            law_slug=law_slug, version_id=version_id, source_url=source_url,
            checksum=checksum, raw_format=raw_format, raw_body=raw_body,
            storage_backend=object_ref.backend if object_ref else None,
            object_key=object_ref.object_key if object_ref else None,
            size_bytes=object_ref.size_bytes if object_ref else None,
        )
        session.add(snapshot)
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            snapshot = session.scalar(select(SourceSnapshot).where(
                SourceSnapshot.law_slug == law_slug, SourceSnapshot.checksum == checksum,
            ).limit(1))
            if not snapshot:
                raise
        return snapshot.id
    finally:
        session.close()


def dispatch_outbox(limit: int = 100, *, mode: str | None = None) -> int:
    redis_url = os.getenv("REDIS_URL", "")
    if not redis_url:
        return 0
    policy = background_backfill_mode(mode)
    from redis import Redis
    redis = Redis.from_url(redis_url, decode_responses=True, socket_connect_timeout=2, socket_timeout=2)
    session = SessionLocal()
    dispatched = 0
    try:
        backfill = or_(HydrationJob.message.like(f"{BACKGROUND_BACKFILL_MARKER}%"),
                       HydrationJob.message.in_(LEGACY_BACKFILL_MESSAGES))
        interactive = or_(HydrationJob.message.in_(INTERACTIVE_JOB_MESSAGES),
                          HydrationJob.message.like(f"{INTERACTIVE_JOB_MARKER}%"))
        terminal = HydrationJob.status.in_(["succeeded", "failed", "cancelled"])
        eligible = (HydrationJob.id.is_not(None) if policy == "continuous" else
                    or_(terminal, interactive, and_(backfill, Law.hot.is_(True))) if policy == "hot" else
                    or_(terminal, interactive))
        events = list(session.scalars(
            select(JobOutbox)
            .join(HydrationJob, HydrationJob.id == JobOutbox.job_id)
            .join(Law, Law.slug == HydrationJob.law_slug)
            .where(JobOutbox.dispatched_at.is_(None),
                   JobOutbox.available_at <= datetime.now(timezone.utc), eligible)
            .order_by(JobOutbox.id).limit(limit).with_for_update(skip_locked=True)
        ))
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
        job.message = _job_message(job, message)
    if error is not None:
        job.error = error
    if status in {"succeeded", "failed", "cancelled"}:
        job.lease_until = None
    job.updated_at = datetime.now(timezone.utc)
    session.commit()


def _process_history_job(job_id: str) -> None:
    from app.sources.normas import SourceDocumentUnavailable

    session = SessionLocal()
    try:
        job = session.get(HydrationJob, job_id)
        law = session.get(Law, job.law_slug) if job else None
        if not job or not law:
            raise ValueError("Job ou norma não encontrados.")
        normas_history = None
        normas_changes = []
        provider = ""
        provenance = None
        if law.source_name in {"Presidência da República — Planalto", "Senado Federal — Dados Abertos Legislativos"}:
            from app.sources.senado import fetch_norm_xml, parse_relation_xml
            from app.sources.normas import fetch_normas_history

            _update_job(session, job, stage=1, message="Consultando histórico oficial do Senado")
            body, list_url = fetch_norm_xml(
                law.law_type, law.number, law.year, source_url=law.fetch_url,
            )
            checksum = hashlib.sha256(body).hexdigest()
            session.commit()
            archive_source_document(law.slug, list_url, checksum, "application/xml; charset=utf-8",
                                   body, law.current_version_id)
            relations = parse_relation_xml(body, expected_number=law.number)
            provider = "senado"
            try:
                normas_history = fetch_normas_history(
                    law.fetch_url, law.law_type, law.number, law.year, senate_detail_xml=body,
                )
                session.commit()
                archive_source_document(
                    law.slug, normas_history.source_url,
                    hashlib.sha256(normas_history.body).hexdigest(), "application/json; charset=utf-8",
                    normas_history.body, law.current_version_id,
                )
                normas_changes = normas_history.changes
            except SourceDocumentUnavailable as exc:
                logger.info("history_text_metadata_unavailable law_id=%s reason=%s", law.slug, str(exc)[:200])
        elif law.source_name == "Assembleia Legislativa do Estado de São Paulo — ALESP":
            from app.sources.alesp import fetch_alesp_history

            _update_job(session, job, stage=1, message="Consultando anotações oficiais de alteração da ALESP")
            snapshot = fetch_alesp_history(law.source_url, law.law_type, law.number, law.year)
            session.commit()
            archive_source_document(law.slug, snapshot.source_url, hashlib.sha256(snapshot.body).hexdigest(),
                                   "application/json; charset=utf-8", snapshot.body, law.current_version_id)
            relations = snapshot.relations
            provenance = snapshot.provenance
            provider = "alesp"
        elif law.source_name == "Sistema Integrado de Normas Jurídicas do Distrito Federal — SINJ-DF":
            from app.sources.sinj_df import fetch_sinj_df_history

            _update_job(session, job, stage=1, message="Consultando relações oficiais do SINJ-DF")
            snapshot = fetch_sinj_df_history(law.source_url, law.law_type, law.number, law.year)
            session.commit()
            archive_source_document(law.slug, snapshot.source_url, hashlib.sha256(snapshot.body).hexdigest(),
                                   "text/html; charset=utf-8", snapshot.body, law.current_version_id)
            relations = snapshot.relations
            provider = "sinj_df"
        elif law.source_name.endswith(" — SAPL"):
            from app.sources.sapl import fetch_sapl_history

            coverage_source = law.coverage or {}
            municipality = coverage_source.get("municipality_ibge_code", "")
            scope_kind = coverage_source.get("sapl_source_scope_kind", "municipality")
            scope_name = "estadual" if scope_kind == "state" else "municipal"
            _update_job(session, job, stage=1, message=f"Consultando relações oficiais do SAPL {scope_name}")
            snapshot = fetch_sapl_history(law.source_url, law.law_type, law.number, law.year)
            session.commit()
            archive_source_document(law.slug, snapshot.source_url, hashlib.sha256(snapshot.body).hexdigest(),
                                   "application/json; charset=utf-8", snapshot.body, law.current_version_id)
            relations = snapshot.relations
            if scope_kind == "state":
                provider = f"sapl:state:{law.state_code or coverage_source.get('sapl_source_ibge_code', '')}"
            elif municipality:
                provider = f"sapl:municipality:{municipality}"
            else:
                provider = "sapl_municipal"
        else:
            raise SourceDocumentUnavailable(f"A fonte {law.source_name} não oferece adapter de histórico.")
        current_version = session.get(LawVersion, law.current_version_id) if law.current_version_id else None
        _update_job(session, job, stage=2,
                    message=f"Conferindo {len(relations)} referências e {len(normas_changes)} versões de dispositivos")
        created = 0
        for relation in relations:
            event = HistoryEvent(
                id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"{provider}:{law.slug}:{relation.source_id}:{relation.device_ref}")),
                law_slug=law.slug, source_id=relation.source_id, device_ref=relation.device_ref,
                relation=relation.relation, event_label=relation.event_label,
                event_url=(getattr(relation, "event_url", "")
                           or f"https://legis.senado.leg.br/dadosabertos/legislacao/{relation.source_id}"),
                signed_at=relation.signed_at, publication_date=relation.publication_date,
                evidence=relation.evidence, status="discovered",
            )
            exists = session.scalar(select(HistoryEvent.id).where(
                HistoryEvent.law_slug == law.slug, HistoryEvent.source_id == relation.source_id,
                HistoryEvent.device_ref == relation.device_ref).limit(1))
            if not exists:
                session.add(event)
                created += 1
        session.flush()

        linked_changes = _persist_normas_text_changes(session, law, current_version, normas_changes)
        if normas_changes:
            relation_events = list(session.scalars(select(HistoryEvent).where(HistoryEvent.law_slug == law.slug)))
            for change in normas_changes:
                matching_events = [event for event in relation_events if _history_event_matches_change(event, change)]
                if matching_events:
                    for event in matching_events:
                        event.status = "compared"
                else:
                    source_id = "normas:" + re.split(r"[@!]", change.source_urn, maxsplit=1)[0]
                    event_id = str(uuid.uuid5(uuid.NAMESPACE_URL,
                                              f"normas:{law.slug}:{source_id}:{change.node_id}"))
                    existing = session.scalar(select(HistoryEvent.id).where(HistoryEvent.id == event_id).limit(1))
                    if not existing:
                        session.add(HistoryEvent(
                            id=event_id, law_slug=law.slug, source_id=source_id,
                            device_ref=change.node_id, relation=change.operation,
                            event_label=change.source_law_label, event_url=change.source_url,
                            signed_at=change.changed_at, publication_date=None,
                            evidence=f"Normas.leg.br: {change.operation}; {change.source_urn}",
                            status="compared",
                        ))
        coverage = dict(law.coverage or {})
        # Official links identify candidate events; only Senate/Normas text pairs
        # are compared here, and none proves every effective date.
        coverage["history"] = "partial"
        coverage["history_source"] = "senado+normas" if normas_history else provider
        coverage["history_checked_at"] = datetime.now(timezone.utc).isoformat()
        coverage["history_relation_count"] = len(relations)
        session.flush()
        pending_text = session.scalar(select(func.count()).select_from(HistoryEvent).where(
            HistoryEvent.law_slug == law.slug, HistoryEvent.status != "compared",
        )) or 0
        coverage["history_events_pending_text"] = pending_text
        coverage["history_comparison_count"] = linked_changes
        coverage["history_effective_dates"] = "not_verified"
        if normas_history:
            coverage["history_text_source"] = {
                "provider": "Normas.leg.br / Senado Federal",
                "urn": normas_history.urn,
                "metadata_url": normas_history.source_url,
                "legal_value": "UnofficialLegalValue",
                "notice": "O portal classifica as transcrições como valor jurídico não oficial; datas de vigência ainda exigem confirmação.",
            }
        elif provider == "senado":
            coverage["history_text_source"] = {"status": "unavailable"}
        else:
            coverage["history_text_source"] = {"provider": provider, "status": "official_relations_only",
                                                "text_comparison": "not_available_from_this_endpoint"}
        if provenance:
            coverage["source_provenance"] = provenance
        law.coverage = coverage
        job.status = "succeeded"
        job.stage = 5
        job.stage_name = "discovered"
        if provider == "senado":
            job.message = _job_message(job, f"{len(relations)} referências oficiais e {linked_changes} comparações textuais verificadas; "
                                       f"{pending_text} referências continuam sem redação conferida")
        else:
            job.message = _job_message(job, f"{len(relations)} referências oficiais registradas nesta fonte; "
                                       "ela não fornece redações anteriores suficientes para comparar cada alteração")
        job.error = ""
        job.lease_until = None
        job.updated_at = datetime.now(timezone.utc)
        session.commit()
        logger.info("history_relations_discovered provider=%s law_id=%s found=%s added=%s text_changes=%s pending=%s",
                    provider, law.slug, len(relations), created, linked_changes, pending_text)
    finally:
        session.close()


def _process_senate_provenance_job(job_id: str) -> None:
    session = SessionLocal()
    try:
        job = session.get(HydrationJob, job_id)
        law = session.get(Law, job.law_slug) if job else None
        if not job or not law:
            raise ValueError("Job ou norma não encontrados.")
        _update_job(session, job, stage=1, message="Consultando tramitação oficial do Senado")
        from app.sources.senado_proceedings import fetch_senate_proceedings

        def archive(document) -> None:
            archive_source_document(
                law.slug, document.url, hashlib.sha256(document.body).hexdigest(),
                "application/json; charset=utf-8", document.body, law.current_version_id,
            )

        data, documents = fetch_senate_proceedings(law.law_type, law.number, law.year,
                                                   on_document=archive)
        _update_job(session, job, stage=4, message="Arquivando processos, emendas e votações oficiais")
        dossier = session.get(SenateProceeding, law.slug)
        if dossier is None:
            dossier = SenateProceeding(law_slug=law.slug)
            session.add(dossier)
        dossier.status = data["status"]
        dossier.data = data
        dossier.checked_at = datetime.now(timezone.utc)
        dossier.error = ""
        coverage = dict(law.coverage or {})
        coverage["senate_provenance"] = data["status"]
        coverage["senate_provenance_checked_at"] = dossier.checked_at.isoformat()
        coverage.pop("senate_provenance_error", None)
        law.coverage = coverage
        job.status = "succeeded"
        job.stage = 5
        job.stage_name = "complete"
        if data["status"] == "no_process":
            job.message = _job_message(job, "Consulta exata ao Senado concluída; nenhum processo vinculado foi listado")
        else:
            process_count = data.get("processes_loaded", 0)
            amendment_count = sum(len(item.get("amendments", [])) for item in data.get("processes", []))
            vote_count = sum(len(item.get("committee_votes", [])) + len(item.get("plenary_votes", []))
                             for item in data.get("processes", []))
            job.message = _job_message(job, f"{process_count} processo(s), {amendment_count} emenda(s) e "
                                       f"{vote_count} sessão(ões) de votação consultados no Senado")
        job.error = ""
        job.lease_until = None
        job.updated_at = datetime.now(timezone.utc)
        session.commit()
        logger.info("senate_provenance_finished law_id=%s status=%s processes=%s documents=%s",
                    law.slug, dossier.status, len(data.get("processes", [])), len(documents))
    finally:
        session.close()


def _persist_normas_text_changes(session, law: Law, current_version: LawVersion | None, changes) -> int:
    compared = 0
    source_version_url = current_version.source_url if current_version else law.source_url
    operation_labels = {"Text_Change": "Alteração", "Insertion": "Inclusão", "Repeal": "Revogação"}
    for change in changes:
        existing = session.scalar(select(LawChange.id).where(
            LawChange.law_slug == law.slug,
            LawChange.node_id == change.node_id,
            LawChange.source_law_number == change.source_law_number,
            LawChange.source_law_year == change.source_law_year,
        ).limit(1))
        compared += 1
        if existing:
            continue
        change_type = {"Text_Change": "UPDATE", "Insertion": "ADD", "Repeal": "REPEAL"}[change.operation]
        session.add(LawChange(
            id=str(uuid.uuid5(uuid.NAMESPACE_URL,
                              f"normas-change:{law.slug}:{change.node_id}:{change.source_law_number}:{change.source_law_year}")),
            law_slug=law.slug, node_id=change.node_id, change_type=change_type,
            summary=f"{operation_labels[change.operation]}: {change.node_label}",
            changed_at=change.changed_at, source_law_label=change.source_law_label,
            source_law_number=change.source_law_number, source_law_year=change.source_law_year,
            source_url=change.source_url, law_source_url=source_version_url,
            before_text=change.before_text, after_text=change.after_text,
            evidence_marker=f"Normas.leg.br; versão por dispositivo: {change.source_urn}",
        ))
    return compared


def _history_event_matches_change(event: HistoryEvent, change) -> bool:
    number_match = re.search(r"n[º°o]?\s*([\d.]+(?:-\d+)?)", event.event_label, re.I)
    year_values = re.findall(r"\b(?:18|19|20|21)\d{2}\b", event.event_label)
    if not number_match or not year_values:
        return False
    event_number = re.sub(r"\D", "", number_match.group(1))
    change_number = re.sub(r"\D", "", change.source_law_number)
    if event_number != change_number or int(year_values[-1]) != change.source_law_year:
        return False
    reference = event.device_ref.split(" [", 1)[0]
    article = re.search(r"\bArt(?:igo)?\.?\s*((?:\d{1,3}(?:\.\d{3})+|\d+)(?:-[A-Za-z])?)", reference, re.I)
    if not article:
        return False
    article_id = f"art:{re.sub(r'[^\da-z-]', '', article.group(1).casefold())}"
    target = change.node_id
    if target != article_id and not target.startswith(article_id + "."):
        return False
    inciso = re.search(r"\bInciso\s+(\d+|[IVXLCDM]+)\b", reference, re.I)
    if inciso:
        value = inciso.group(1).upper()
        if value.isdigit():
            value = _roman_number(int(value))
        if f".inciso:{value}" not in target:
            return False
    paragraph = re.search(r"§\s*(\d+)|Parágrafo\s+Único", reference, re.I)
    if paragraph:
        value = "unico" if "único" in reference.casefold() else str(int(paragraph.group(1)))
        if f".par:{value}" not in target:
            return False
    alinea = re.search(r"\bal[ií]nea\s+([a-z])\b", reference, re.I)
    if alinea and f".alinea:{alinea.group(1).casefold()}" not in target:
        return False
    return True


def _roman_number(value: int) -> str:
    numerals = ((1000, "M"), (900, "CM"), (500, "D"), (400, "CD"), (100, "C"),
                (90, "XC"), (50, "L"), (40, "XL"), (10, "X"), (9, "IX"),
                (5, "V"), (4, "IV"), (1, "I"))
    result = []
    for amount, numeral in numerals:
        while value >= amount:
            result.append(numeral)
            value -= amount
    return "".join(result)


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
        elif job_type == "provenance":
            _process_senate_provenance_job(job_id)
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
            if failed.attempts < 5 and outbox and not isinstance(exc, SourceDocumentUnavailable):
                delay = min(3600, 15 * (2 ** max(0, failed.attempts - 1)))
                failed.status = "queued"
                failed.stage_name = "retry_wait"
                failed.message = _job_message(failed, f"Fonte temporariamente indisponível; nova tentativa em aproximadamente {delay} s")
                outbox.available_at = datetime.now(timezone.utc) + timedelta(seconds=delay)
                outbox.dispatched_at = None
                outbox.last_error = failed.error
            else:
                failed.status = "failed"
                failed.stage_name = "failed"
                failed.message = _job_message(failed, (
                    "A fonte oficial não fornece um texto compatível"
                    if isinstance(exc, SourceDocumentUnavailable) else
                    "O processamento falhou após novas tentativas"
                ))
                law = retry_session.get(Law, failed.law_slug)
                if law:
                    if failed.job_type == "history":
                        coverage = dict(law.coverage or {})
                        coverage["history"] = "unavailable" if coverage.get("history") in {None, "queued"} else "partial"
                        coverage["history_error"] = failed.error[:500]
                        law.coverage = coverage
                    elif failed.job_type == "provenance":
                        coverage = dict(law.coverage or {})
                        dossier = retry_session.get(SenateProceeding, law.slug)
                        if dossier and dossier.status in {"complete", "partial", "no_process"}:
                            coverage["senate_provenance"] = dossier.status
                        else:
                            coverage["senate_provenance"] = "failed"
                        coverage["senate_provenance_error"] = failed.error[:500]
                        law.coverage = coverage
                        if dossier:
                            dossier.error = failed.error[:1000]
                    elif isinstance(exc, SourceDocumentUnavailable):
                        coverage = dict(law.coverage or {})
                        coverage["structured_text"] = "partial" if law.current_version_id else "unavailable"
                        coverage["text_source_status"] = "unavailable"
                        coverage["text_source_error"] = failed.error[:500]
                        law.coverage = coverage
                        law.materialization_status = "partial" if law.current_version_id else "unavailable"
                    elif not law.current_version_id:
                        law.materialization_status = "catalog"
                        coverage = dict(law.coverage or {})
                        coverage["text_source_status"] = "retryable"
                        coverage["text_source_error"] = failed.error[:500]
                        coverage["text_source_retry_after"] = (
                            datetime.now(timezone.utc) + timedelta(hours=6)
                        ).isoformat()
                        law.coverage = coverage
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
    from app.sources.normas import fetch_senado_document

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
        if not law.current_version_id:
            law.materialization_status = "preparing"
        session.commit()
        logger.info("hydration_started source=%s job=%s jurisdiction=%s law_id=%s", law.source_name, job.id, law.jurisdiction, law.slug)

        _update_job(session, job, stage=2, message="Obtendo texto da fonte oficial")
        source_metadata = None
        if law.source_name == "Presidência da República — Planalto":
            body, fetched_url = fetch_official_html(law.fetch_url)
        elif law.source_name == "Senado Federal — Dados Abertos Legislativos":
            document = fetch_senado_document(law.fetch_url, law.law_type, law.number, law.year)
            body, fetched_url = document.body, document.source_url
            source_metadata = document
        elif law.source_name == "Assembleia Legislativa do Estado de São Paulo — ALESP":
            from app.sources.alesp import fetch_alesp_document

            document = fetch_alesp_document(law.source_url, law.law_type, law.number, law.year)
            body, fetched_url = document.body, document.source_url
            source_metadata = document
        elif law.source_name == "Sistema Integrado de Normas Jurídicas do Distrito Federal — SINJ-DF":
            from app.sources.sinj_df import fetch_sinj_df_document

            document = fetch_sinj_df_document(law.source_url, law.law_type, law.number, law.year)
            body, fetched_url = document.body, document.source_url
            source_metadata = document
        elif law.source_name.endswith(" — SAPL"):
            from app.sources.sapl import fetch_sapl_document

            document = fetch_sapl_document(law.source_url, law.law_type, law.number, law.year)
            body, fetched_url = document.body, document.source_url
            source_metadata = document
        else:
            from app.sources.normas import SourceDocumentUnavailable
            raise SourceDocumentUnavailable(f"Não existe adapter de texto integral para {law.source_name}.")
        checksum = hashlib.sha256(body).hexdigest()
        parsing_body = getattr(source_metadata, "parsed_body", None) or body
        archive_source_document(law.slug, fetched_url, checksum, detect_raw_format(body), body,
                               law.current_version_id)

        version = session.scalar(select(LawVersion).where(
            LawVersion.law_slug == law.slug, LawVersion.checksum == checksum,
            LawVersion.parser_version == PARSER_VERSION,
        ).limit(1))
        if version:
            session.query(LawVersion).filter(LawVersion.law_slug == law.slug, LawVersion.id != version.id).update({"is_current": False})
            version.is_current = True
            nodes = list(session.scalars(select(LegalNode).where(LegalNode.version_id == version.id).order_by(LegalNode.order_index)))
        else:
            _update_job(session, job, stage=3, message="Estruturando artigos e dispositivos")
            parsed = parse_legal_nodes(parsing_body)
            unstructured_full_text = False
            if not parsed:
                paragraphs = extract_paragraphs(parsing_body)
                full_text = "\n".join(text.strip() for text, _raw in paragraphs if text.strip())
                if not full_text:
                    raise SourceDocumentUnavailable("A fonte respondeu sem texto integral legível para materializar.")
                parsed = [ParsedNode(
                    node_id="document:full-text", parent_node_id=None, node_type="document",
                    label="Texto integral — estrutura não reconhecida", text=full_text,
                    source_note="Texto extraído integralmente da captura arquivada; artigos e dispositivos não foram estruturados.",
                    order_index=1,
                )]
                unstructured_full_text = True
            session.query(LawVersion).filter(LawVersion.law_slug == law.slug).update({"is_current": False})
            version = LawVersion(
                law_slug=law.slug,
                version_name=((
                    "Texto compilado consultado no Planalto"
                    if source_metadata is None else
                    f"{source_metadata.version} — "
                    + (
                        "publicação original no DOU"
                        if source_metadata.source_url.startswith("https://www.in.gov.br/web/dou/-/") else
                        source_metadata.representation
                        if (source_metadata.source_url.startswith("https://www.al.sp.gov.br/repositorio/legislacao/")
                            or source_metadata.source_url.startswith("https://www.sinj.df.gov.br/sinj/Norma/")
                            or law.source_name.endswith(" — SAPL")) else
                        "compilação atual do Normas.leg.br"
                        if source_metadata.version == "Current" else
                        "transcrição da publicação original"
                    )
                    + (
                        " (classificação jurídica não informada)"
                        if source_metadata.legal_value not in {"OfficialLegalValue", "NonOfficialLegalValue"} else
                        " (valor jurídico oficial)"
                        if source_metadata.legal_value == "OfficialLegalValue" else
                        " (valor jurídico não oficial)"
                    )
                ) + (" — estrutura não reconhecida" if unstructured_full_text else ""))[:160],
                source_url=fetched_url,
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
            session.flush()

        archived_snapshot = session.scalar(select(SourceSnapshot).where(
            SourceSnapshot.law_slug == law.slug, SourceSnapshot.checksum == checksum,
        ).limit(1))
        if archived_snapshot and archived_snapshot.version_id is None:
            archived_snapshot.version_id = version.id

        job.stage = 4
        job.stage_name = "validate"
        job.message = _job_message(job, "Conferindo referências de alteração")
        job.updated_at = datetime.now(timezone.utc)
        linked_changes = _verified_lmp_changes(session, law, version, nodes) if law.slug == "11340-2006" else 0
        law.current_version_id = version.id
        # Parsing succeeded, but no independent whole-document completeness audit exists yet.
        law.materialization_status = "partial"
        law.last_hydrated_at = datetime.now(timezone.utc)
        document_audit = audit_archived_document(parsing_body, nodes)
        coverage = dict(law.coverage or {})
        coverage.update({
            "official_source": "available",
            "structured_text": "unstructured" if any(node.node_type == "document" for node in nodes) else "partial",
            "history": "partial" if linked_changes or session.scalar(select(LawChange.id).where(LawChange.law_slug == law.slug).limit(1)) else coverage.get("history", "not_materialized"),
            "attribution": "partial" if linked_changes else "not_identified",
            "authors": "not_available",
            "votes": "not_available",
            "snapshot_checksum": checksum,
            "document_audit": document_audit,
        })
        if source_metadata is not None:
            if source_metadata.source_url.startswith("https://www.in.gov.br/web/dou/-/"):
                provider = "Diário Oficial da União / Senado Federal"
            else:
                provider = {
                    "Senado Federal — Dados Abertos Legislativos": "Senado Federal / Normas.leg.br",
                    "Assembleia Legislativa do Estado de São Paulo — ALESP": "ALESP",
                    "Sistema Integrado de Normas Jurídicas do Distrito Federal — SINJ-DF": "SINJ-DF",
                    "Câmara Municipal de Manaus — SAPL": "Câmara Municipal de Manaus — SAPL",
                }.get(law.source_name, law.source_name)
            coverage["text_source"] = {
                "provider": provider,
                "representation": source_metadata.representation,
                "version": source_metadata.version,
                "legal_value": source_metadata.legal_value,
                "notice": source_metadata.notice,
                "source_url": fetched_url,
            }
        coverage.pop("text_source_error", None)
        coverage["text_source_status"] = "available"
        law.coverage = coverage
        _update_job(session, job, status="succeeded", stage=5,
                    message=(
                        "Texto integral disponível; estrutura jurídica não reconhecida, revisão necessária"
                        if any(node.node_type == "document" for node in nodes) else
                        "Texto e dispositivos disponíveis; cobertura estrutural parcial" if source_metadata else
                        "Texto e dispositivos disponíveis"
                    ))
        session.commit()
        logger.info("hydration_finished source=%s job=%s jurisdiction=%s law_id=%s duration_state=success articles=%s changes=%s checksum=%s",
                    law.source_name, job.id, law.jurisdiction, law.slug, version.article_count, linked_changes, checksum)
    except Exception:
        session.rollback()
        logger.exception("hydration_failed job=%s", job_id)
        raise
    finally:
        session.close()

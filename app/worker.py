import hashlib
import logging
import os
from pathlib import Path
import time
import uuid
from threading import Event, Thread
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed

from app.jobs import (
    MAX_INTERACTIVE_JOB_BATCH,
    QUEUE_GROUP,
    QUEUE_NAME,
    background_backfill_mode,
    dispatch_outbox,
    process_hydration_job,
    queue_official_history_batch,
    queued_interactive_job_ids,
    should_process_job,
)

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(message)s")
logger = logging.getLogger("leiaberta.worker")
MAX_HYDRATION_CONCURRENCY = MAX_INTERACTIVE_JOB_BATCH
MAX_CATALOG_CONCURRENCY = 4
QUEUE_DEPTH_SUMMARY_INTERVAL_SECONDS = 300


def hydration_concurrency() -> int:
    """Allow the network-bound worker to use measured Railway headroom."""
    return min(MAX_HYDRATION_CONCURRENCY, max(1, int(os.getenv("HYDRATION_CONCURRENCY", "8"))))


def catalog_concurrency() -> int:
    """Serialize catalog writers by default; raise this only after measuring DB headroom."""
    return min(MAX_CATALOG_CONCURRENCY, max(1, int(os.getenv("CATALOG_SYNC_CONCURRENCY", "1"))))


def is_transient_worker_error(exc: Exception) -> bool:
    """Recognize database/Redis transport failures without logging their details."""
    from redis.exceptions import ConnectionError as RedisConnectionError
    from redis.exceptions import TimeoutError as RedisTimeoutError
    from sqlalchemy.exc import OperationalError

    if isinstance(exc, (RedisConnectionError, RedisTimeoutError)):
        return True
    if isinstance(exc, OperationalError):
        if exc.connection_invalidated:
            return True
        detail = str(exc.orig).casefold()
        return any(marker in detail for marker in (
            "connection refused", "connection reset", "connection timed out",
            "could not connect", "connection to server", "connection is closed",
            "connection already closed", "terminating connection", "server closed",
            "in recovery", "starting up", "timeout", "timed out",
            "network is unreachable", "broken pipe", "temporarily unavailable",
            "could not receive", "could not send", "too many clients",
        ))
    return False


class WorkerLoopBackoff:
    """Capped retry delays and sparse summaries for repeated transport failures."""

    def __init__(self, initial: float = 3.0, maximum: float = 30.0, log_every: int = 10):
        self.initial = initial
        self.maximum = maximum
        self.log_every = log_every
        self.reset()

    def reset(self) -> None:
        self.delay = self.initial
        self.error_type: str | None = None
        self.error_fingerprint: str | None = None
        self.consecutive = 0
        self.suppressed = 0

    def on_success(self) -> None:
        self.reset()

    def on_error(self, exc: Exception) -> tuple[float, int, int] | None:
        if not is_transient_worker_error(exc):
            self.reset()
            return None
        error_type = type(exc).__name__
        exception_detail = str(getattr(exc, "orig", exc)).encode("utf-8", errors="replace")
        fingerprint = hashlib.sha256(exception_detail).hexdigest()
        if error_type != self.error_type or fingerprint != self.error_fingerprint:
            self.reset()
            self.error_type = error_type
            self.error_fingerprint = fingerprint
        retry_after = self.delay
        self.delay = min(self.delay * 2, self.maximum)
        self.consecutive += 1
        if self.consecutive == 1 or self.consecutive % self.log_every == 0:
            suppressed = self.suppressed
            self.suppressed = 0
            return retry_after, self.consecutive, suppressed
        self.suppressed += 1
        return retry_after, self.consecutive, -1


def publish_worker_heartbeat(redis, consumer: str, concurrency: int,
                             now: datetime | None = None) -> str:
    timestamp = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat()
    redis.set("leiaberta:worker:heartbeat", timestamp, ex=90)
    logger.info("worker_heartbeat consumer=%s concurrency=%s at=%s", consumer, concurrency, timestamp)
    return timestamp


def worker_heartbeat_loop(redis, consumer: str, concurrency: int, stop: Event,
                          interval_seconds: int = 30) -> None:
    """Keep liveness independent of long-running batches on the worker loop."""
    while not stop.is_set():
        try:
            publish_worker_heartbeat(redis, consumer, concurrency)
        except Exception:
            logger.exception("worker_heartbeat_publish_failed")
        if stop.wait(interval_seconds):
            return


def start_worker_heartbeat(redis, consumer: str, concurrency: int) -> tuple[Event, Thread]:
    stop = Event()
    thread = Thread(target=worker_heartbeat_loop, args=(redis, consumer, concurrency, stop),
                    name="worker-heartbeat", daemon=True)
    thread.start()
    return stop, thread


def publish_queue_depth_summary(redis) -> None:
    """Log aggregate Redis queue counts without exposing any job or consumer IDs."""
    try:
        stream_length = int(redis.xlen(QUEUE_NAME))
        pending_summary = redis.xpending(QUEUE_NAME, QUEUE_GROUP)
        pending_count = int(pending_summary.get("pending", 0))
        logger.info("worker_queue_depth stream_length=%s pending_count=%s",
                    stream_length, pending_count)
    except Exception as exc:
        # Telemetry is best-effort and must never interrupt queue work.
        logger.warning("worker_queue_depth_unavailable error_type=%s", type(exc).__name__)


def _is_terminal_job(job_id: str) -> bool:
    """Read terminal job state before submission so stale deliveries need no worker slot."""
    from app.db import SessionLocal
    from app.models import HydrationJob

    with SessionLocal() as session:
        job = session.get(HydrationJob, job_id)
        return bool(job and job.status in {"succeeded", "failed", "cancelled"})


def process_queue_messages(redis, messages, executor: ThreadPoolExecutor, *, backfill_mode: str | None = None) -> None:
    """Process independent source jobs concurrently; ACK only after durable handling."""
    futures = {}
    for message_id, fields in messages:
        job_id = fields.get("job_id")
        if job_id:
            # A terminal delivery is stale and safe to ACK without a processing slot.
            if _is_terminal_job(job_id):
                redis.xack(QUEUE_NAME, QUEUE_GROUP, message_id)
                continue
            # A paused bulk item remains in the stream/DB for a later resume.
            # Do not ACK or claim work by changing its durable job status.
            if not should_process_job(job_id, mode=backfill_mode):
                logger.info("worker_backfill_job_paused job=%s mode=%s", job_id, backfill_mode)
                continue
            futures[executor.submit(process_hydration_job, job_id)] = (message_id, job_id)
        else:
            redis.xack(QUEUE_NAME, QUEUE_GROUP, message_id)
    for future in as_completed(futures):
        message_id, job_id = futures[future]
        try:
            future.result()
        except Exception:
            # Leave the message pending so XAUTOCLAIM can recover it after a worker crash.
            logger.exception("worker_job_unhandled_error job=%s", job_id)
            continue
        redis.xack(QUEUE_NAME, QUEUE_GROUP, message_id)


def process_priority_jobs(job_ids: list[str], executor: ThreadPoolExecutor) -> None:
    """Claim user-triggered work before reading older bulk-backfill entries."""
    futures = {executor.submit(process_hydration_job, job_id): job_id for job_id in job_ids}
    for future in as_completed(futures):
        job_id = futures[future]
        try:
            future.result()
        except Exception:
            logger.exception("worker_priority_job_unhandled_error job=%s", job_id)


def wait_for_database_schema(*, timeout: float = 300, interval: float = 3) -> None:
    """Wait until the web service's startup migrations have created the queue schema."""
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    from sqlalchemy import inspect, text
    from app.db import engine

    alembic_config = Config(str(Path(__file__).resolve().parent.parent / "alembic.ini"))
    expected_heads = set(ScriptDirectory.from_config(alembic_config).get_heads())

    deadline = time.monotonic() + timeout
    attempts = 0
    retry_delay = min(max(float(interval), 0.01), 30.0)
    while True:
        attempts += 1
        try:
            inspector = inspect(engine)
            if inspector.has_table("alembic_version"):
                with engine.connect() as connection:
                    current_heads = set(connection.execute(text("SELECT version_num FROM alembic_version")).scalars())
                if current_heads == expected_heads:
                    if inspector.has_table("hydration_jobs") and inspector.has_table("job_outbox"):
                        if attempts > 1:
                            logger.info("worker_database_ready attempts=%s", attempts)
                        return
            last_error = f"database is not at Alembic head {sorted(expected_heads)}"
        except Exception as exc:
            last_error = f"database check failed ({type(exc).__name__})"
        if time.monotonic() >= deadline:
            raise SystemExit(f"Database schema was not ready before timeout: {last_error}")
        if attempts == 1 or attempts % 10 == 0:
            logger.info("worker_waiting_for_database_schema attempt=%s detail=%s", attempts, last_error)
        remaining = max(0.0, deadline - time.monotonic())
        time.sleep(min(retry_delay, remaining))
        retry_delay = min(retry_delay * 2, 30.0)


def run() -> None:
    redis_url = os.getenv("REDIS_URL")
    if not redis_url:
        logger.error("worker_stopped reason=REDIS_URL_missing")
        raise SystemExit("REDIS_URL is required for the worker service")
    wait_for_database_schema()
    from redis import Redis

    redis = Redis.from_url(redis_url, decode_responses=True, socket_connect_timeout=5, socket_timeout=35)
    consumer = f"worker-{uuid.uuid4()}"
    backfill_mode = background_backfill_mode()
    try:
        redis.xgroup_create(QUEUE_NAME, QUEUE_GROUP, id="0-0", mkstream=True)
    except Exception as exc:
        if "BUSYGROUP" not in str(exc):
            raise
    concurrency = hydration_concurrency()
    logger.info("worker_started queue=%s group=%s consumer=%s concurrency=%s background_backfill_mode=%s",
                QUEUE_NAME, QUEUE_GROUP, consumer, concurrency, backfill_mode)
    executor = ThreadPoolExecutor(max_workers=concurrency, thread_name_prefix="hydration")
    # Catalog adapters write the same primary-key index; serialize them by default
    # to prevent concurrent index-page contention during large imports.
    catalog_workers = catalog_concurrency()
    logger.info("catalog_worker_started concurrency=%s", catalog_workers)
    catalog_executor = ThreadPoolExecutor(max_workers=catalog_workers, thread_name_prefix="catalog-sync")
    senado_sync_future = None
    alesp_sync_future = None
    sinj_sync_future = None
    sapl_sync_future = None
    ibge_sync_future = None
    refresh_check_seconds = max(300, int(os.getenv("CATALOG_REFRESH_CHECK_SECONDS", "3600")))
    next_refresh_check = time.monotonic()
    senado_batch_seconds = max(300, int(os.getenv("SENADO_TEXT_BATCH_SECONDS", "300")))
    senado_batch_size = min(500, max(1, int(os.getenv("SENADO_TEXT_BATCH_SIZE", "500"))))
    next_senado_batch = time.monotonic()
    subnational_batch_seconds = max(300, int(os.getenv("SUBNATIONAL_TEXT_BATCH_SECONDS", "300")))
    subnational_batch_size = min(200, max(1, int(os.getenv("SUBNATIONAL_TEXT_BATCH_SIZE", "200"))))
    next_subnational_batch = time.monotonic()
    history_batch_seconds = max(300, int(os.getenv("HISTORY_BACKFILL_BATCH_SECONDS", "300")))
    history_batch_size = min(500, max(1, int(os.getenv("HISTORY_BACKFILL_BATCH_SIZE", "500"))))
    next_history_batch = time.monotonic()
    next_queue_depth_summary = time.monotonic() + QUEUE_DEPTH_SUMMARY_INTERVAL_SECONDS
    loop_backoff = WorkerLoopBackoff()
    start_worker_heartbeat(redis, consumer, concurrency)
    while True:
        try:
            if senado_sync_future is not None and senado_sync_future.done():
                try:
                    result = senado_sync_future.result()
                    logger.info("senado_catalog_refresh_finished listed=%s skipped=%s errors=%s",
                                result["listed"], len(result["skipped_fresh"]), len(result["errors"]))
                    if result["errors"]:
                        next_refresh_check = min(next_refresh_check, time.monotonic() + 300)
                except Exception:
                    logger.exception("senado_catalog_refresh_failed")
                    next_refresh_check = min(next_refresh_check, time.monotonic() + 300)
                senado_sync_future = None
            if ibge_sync_future is not None and ibge_sync_future.done():
                try:
                    result = ibge_sync_future.result()
                    logger.info("ibge_jurisdictions_refresh_finished result=%s",
                                "skipped_fresh" if result.get("skipped_fresh") else result.get("localities", 0))
                except Exception:
                    logger.exception("ibge_jurisdictions_refresh_failed")
                    next_refresh_check = min(next_refresh_check, time.monotonic() + 300)
                ibge_sync_future = None
            if alesp_sync_future is not None and alesp_sync_future.done():
                try:
                    result = alesp_sync_future.result()
                    logger.info("alesp_catalog_sync_finished records=%s added=%s refreshed=%s skipped_fresh=%s",
                                result.get("records", 0), result.get("added", 0),
                                result.get("refreshed", 0), result.get("skipped_fresh", False))
                except Exception:
                    logger.exception("alesp_catalog_sync_failed")
                    next_refresh_check = min(next_refresh_check, time.monotonic() + 300)
                alesp_sync_future = None
            if sinj_sync_future is not None and sinj_sync_future.done():
                try:
                    result = sinj_sync_future.result()
                    logger.info("sinj_df_catalog_sync_finished records=%s added=%s refreshed=%s skipped_fresh=%s",
                                result.get("records", 0), result.get("added", 0),
                                result.get("refreshed", 0), result.get("skipped_fresh", False))
                except Exception:
                    logger.exception("sinj_df_catalog_sync_failed")
                    next_refresh_check = min(next_refresh_check, time.monotonic() + 300)
                sinj_sync_future = None
            if sapl_sync_future is not None and sapl_sync_future.done():
                try:
                    result = sapl_sync_future.result()
                    logger.info("sapl_catalog_sync_finished records=%s sources=%s errors=%s skipped_fresh=%s",
                                result.get("records", 0), len(result.get("synced", [])),
                                len(result.get("errors", [])), result.get("skipped_fresh", 0))
                    if result.get("errors"):
                        next_refresh_check = min(next_refresh_check, time.monotonic() + 300)
                except Exception:
                    logger.exception("sapl_manaus_catalog_sync_failed")
                    next_refresh_check = min(next_refresh_check, time.monotonic() + 300)
                sapl_sync_future = None
            if backfill_mode != "off" and time.monotonic() >= next_senado_batch:
                next_senado_batch = time.monotonic() + senado_batch_seconds
                try:
                    from app.jobs import queue_senado_text_batch

                    result = queue_senado_text_batch(limit=senado_batch_size, mode=backfill_mode)
                    if result["queued_count"]:
                        logger.info("senado_text_backfill_enqueued count=%s batch_limit=%s",
                                    result["queued_count"], senado_batch_size)
                    elif result.get("capacity_reached"):
                        logger.info("senado_text_backfill_paused active_jobs=%s active_limit=%s",
                                    result["active_jobs"], result["active_job_limit"])
                except Exception:
                    logger.exception("senado_text_backfill_enqueue_failed")
            if backfill_mode != "off" and time.monotonic() >= next_subnational_batch:
                next_subnational_batch = time.monotonic() + subnational_batch_seconds
                try:
                    from app.jobs import queue_subnational_text_batch

                    result = queue_subnational_text_batch(limit=subnational_batch_size, mode=backfill_mode)
                    if result["queued_count"]:
                        logger.info("subnational_text_backfill_enqueued count=%s by_source=%s",
                                    result["queued_count"], result["queued_by_source"])
                    elif result.get("capacity_reached"):
                        logger.info("subnational_text_backfill_paused active_jobs=%s active_limit=%s",
                                    result["active_jobs"], result["active_job_limit"])
                except Exception:
                    logger.exception("subnational_text_backfill_enqueue_failed")
            if backfill_mode != "off" and time.monotonic() >= next_history_batch:
                next_history_batch = time.monotonic() + history_batch_seconds
                try:
                    result = queue_official_history_batch(limit=history_batch_size, mode=backfill_mode)
                    if result["queued_count"]:
                        logger.info("official_history_backfill_enqueued count=%s by_source=%s",
                                    result["queued_count"], result["queued_by_source"])
                    elif result.get("capacity_reached"):
                        logger.info("official_history_backfill_paused active_jobs=%s active_limit=%s",
                                    result["active_jobs"], result["active_job_limit"])
                except Exception:
                    logger.exception("official_history_backfill_enqueue_failed")
            if time.monotonic() >= next_refresh_check:
                next_refresh_check = time.monotonic() + refresh_check_seconds
                try:
                    from app.catalog_sync.senado import sync_senado_law_catalog

                    if senado_sync_future is None:
                        senado_sync_future = catalog_executor.submit(sync_senado_law_catalog)
                        logger.info("senado_catalog_refresh_started")
                except Exception:
                    logger.exception("senado_catalog_refresh_start_failed")
                if ibge_sync_future is None:
                    try:
                        from app.catalog_sync.ibge import sync_ibge_jurisdictions

                        ibge_sync_future = catalog_executor.submit(sync_ibge_jurisdictions)
                        logger.info("ibge_jurisdictions_refresh_started")
                    except Exception:
                        logger.exception("ibge_jurisdictions_refresh_start_failed")
                if alesp_sync_future is None:
                    try:
                        from app.catalog_sync.alesp import sync_alesp_catalog

                        alesp_sync_future = catalog_executor.submit(sync_alesp_catalog)
                    except Exception:
                        logger.exception("alesp_catalog_refresh_start_failed")
                if sinj_sync_future is None:
                    try:
                        from app.catalog_sync.sinj_df import sync_sinj_df_catalog

                        sinj_sync_future = catalog_executor.submit(sync_sinj_df_catalog)
                    except Exception:
                        logger.exception("sinj_df_catalog_refresh_start_failed")
                if sapl_sync_future is None:
                    try:
                        from app.catalog_sync.sapl import sync_all_sapl_catalogs

                        sapl_sync_future = catalog_executor.submit(sync_all_sapl_catalogs)
                    except Exception:
                        logger.exception("sapl_manaus_catalog_refresh_start_failed")
            if time.monotonic() >= next_queue_depth_summary:
                next_queue_depth_summary = time.monotonic() + QUEUE_DEPTH_SUMMARY_INTERVAL_SECONDS
                publish_queue_depth_summary(redis)
            priority_job_ids = queued_interactive_job_ids(limit=concurrency)
            if priority_job_ids:
                process_priority_jobs(priority_job_ids, executor)
                loop_backoff.on_success()
                continue
            dispatch_outbox(mode=backfill_mode)
            claimed = redis.xautoclaim(QUEUE_NAME, QUEUE_GROUP, consumer, min_idle_time=300_000,
                                       start_id="0-0", count=concurrency)
            messages = claimed[1] if claimed and len(claimed) > 1 else []
            if not messages:
                batch = redis.xreadgroup(QUEUE_GROUP, consumer, {QUEUE_NAME: ">"}, count=concurrency, block=5000)
                messages = batch[0][1] if batch else []
            process_queue_messages(redis, messages, executor, backfill_mode=backfill_mode)
        except Exception as exc:
            retry = loop_backoff.on_error(exc)
            if retry is None:
                logger.exception("worker_queue_error queue=%s", QUEUE_NAME)
                time.sleep(3)
                continue
            retry_after, consecutive, suppressed = retry
            if suppressed >= 0:
                logger.error(
                    "worker_transient_error type=%s consecutive=%s suppressed=%s retry_in_seconds=%s",
                    type(exc).__name__, consecutive, suppressed, retry_after,
                )
            time.sleep(retry_after)
        else:
            loop_backoff.on_success()


if __name__ == "__main__":
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(message)s")
    run()

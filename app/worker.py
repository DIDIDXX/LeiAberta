import logging
import os
from pathlib import Path
import time
import uuid

from app.jobs import QUEUE_GROUP, QUEUE_NAME, dispatch_outbox, process_hydration_job

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(message)s")
logger = logging.getLogger("leiaberta.worker")


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
            last_error = str(exc)[:200]
        if time.monotonic() >= deadline:
            raise SystemExit(f"Database schema was not ready before timeout: {last_error}")
        if attempts == 1 or attempts % 10 == 0:
            logger.info("worker_waiting_for_database_schema attempt=%s detail=%s", attempts, last_error)
        time.sleep(interval)


def run() -> None:
    redis_url = os.getenv("REDIS_URL")
    if not redis_url:
        logger.error("worker_stopped reason=REDIS_URL_missing")
        raise SystemExit("REDIS_URL is required for the worker service")
    wait_for_database_schema()
    from redis import Redis

    redis = Redis.from_url(redis_url, decode_responses=True, socket_connect_timeout=5, socket_timeout=35)
    consumer = f"worker-{uuid.uuid4()}"
    try:
        redis.xgroup_create(QUEUE_NAME, QUEUE_GROUP, id="0-0", mkstream=True)
    except Exception as exc:
        if "BUSYGROUP" not in str(exc):
            raise
    logger.info("worker_started queue=%s group=%s consumer=%s", QUEUE_NAME, QUEUE_GROUP, consumer)
    refresh_check_seconds = max(300, int(os.getenv("CATALOG_REFRESH_CHECK_SECONDS", "3600")))
    next_refresh_check = time.monotonic() + refresh_check_seconds
    senado_batch_seconds = max(300, int(os.getenv("SENADO_TEXT_BATCH_SECONDS", "300")))
    senado_batch_size = min(500, max(1, int(os.getenv("SENADO_TEXT_BATCH_SIZE", "100"))))
    next_senado_batch = time.monotonic()
    while True:
        try:
            if time.monotonic() >= next_senado_batch:
                next_senado_batch = time.monotonic() + senado_batch_seconds
                try:
                    from app.jobs import queue_senado_text_batch

                    result = queue_senado_text_batch(limit=senado_batch_size)
                    if result["queued_count"]:
                        logger.info("senado_text_backfill_enqueued count=%s batch_limit=%s",
                                    result["queued_count"], senado_batch_size)
                except Exception:
                    logger.exception("senado_text_backfill_enqueue_failed")
            if time.monotonic() >= next_refresh_check:
                next_refresh_check = time.monotonic() + refresh_check_seconds
                try:
                    from app.catalog_sync.ibge import sync_ibge_jurisdictions
                    from app.catalog_sync.senado import sync_senado_law_catalog

                    senado = sync_senado_law_catalog()
                    ibge = sync_ibge_jurisdictions()
                    logger.info("scheduled_source_refresh senate_synced=%s senate_skipped=%s senate_errors=%s ibge=%s",
                                senado["listed"], len(senado["skipped_fresh"]), len(senado["errors"]),
                                "skipped_fresh" if ibge.get("skipped_fresh") else ibge.get("localities", 0))
                except Exception:
                    logger.exception("scheduled_source_refresh_failed")
            dispatch_outbox()
            claimed = redis.xautoclaim(QUEUE_NAME, QUEUE_GROUP, consumer, min_idle_time=300_000, start_id="0-0", count=10)
            messages = claimed[1] if claimed and len(claimed) > 1 else []
            if not messages:
                batch = redis.xreadgroup(QUEUE_GROUP, consumer, {QUEUE_NAME: ">"}, count=10, block=5000)
                messages = batch[0][1] if batch else []
            for message_id, fields in messages:
                job_id = fields.get("job_id")
                if job_id:
                    process_hydration_job(job_id)
                redis.xack(QUEUE_NAME, QUEUE_GROUP, message_id)
        except Exception:
            logger.exception("worker_queue_error queue=%s", QUEUE_NAME)
            time.sleep(3)


if __name__ == "__main__":
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(message)s")
    run()

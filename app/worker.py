import logging
import os
import time
import uuid

from app.jobs import QUEUE_GROUP, QUEUE_NAME, dispatch_outbox, process_hydration_job

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(message)s")
logger = logging.getLogger("leiaberta.worker")


def run() -> None:
    redis_url = os.getenv("REDIS_URL")
    if not redis_url:
        logger.error("worker_stopped reason=REDIS_URL_missing")
        raise SystemExit("REDIS_URL is required for the worker service")
    from redis import Redis

    redis = Redis.from_url(redis_url, decode_responses=True, socket_connect_timeout=5, socket_timeout=35)
    consumer = f"worker-{uuid.uuid4()}"
    try:
        redis.xgroup_create(QUEUE_NAME, QUEUE_GROUP, id="0-0", mkstream=True)
    except Exception as exc:
        if "BUSYGROUP" not in str(exc):
            raise
    logger.info("worker_started queue=%s group=%s consumer=%s", QUEUE_NAME, QUEUE_GROUP, consumer)
    while True:
        try:
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

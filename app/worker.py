import logging
import os
import time

from app.jobs import QUEUE_NAME, process_hydration_job

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(message)s")
logger = logging.getLogger("leiaberta.worker")


def run() -> None:
    redis_url = os.getenv("REDIS_URL")
    if not redis_url:
        logger.error("worker_stopped reason=REDIS_URL_missing")
        raise SystemExit("REDIS_URL is required for the worker service")
    from redis import Redis

    redis = Redis.from_url(redis_url, decode_responses=True, socket_connect_timeout=5, socket_timeout=35)
    logger.info("worker_started queue=%s", QUEUE_NAME)
    while True:
        try:
            item = redis.blpop(QUEUE_NAME, timeout=25)
            if item:
                _, job_id = item
                process_hydration_job(job_id)
        except Exception:
            logger.exception("worker_queue_error queue=%s", QUEUE_NAME)
            time.sleep(3)


if __name__ == "__main__":
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(message)s")
    run()

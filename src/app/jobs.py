"""In-process async job queue. Single worker by default (configurable via
MAX_CONCURRENT_DOWNLOADS), matching the "schema + single-worker engine
first" design principle before layering concurrency.
"""
from __future__ import annotations

import asyncio
import json

from app.config import settings
from app.database import get_session, Job, StorageTarget
from app.downloader import run_download_job
from app.exporter import run_export_job
from app.forwarder import run_forward_job
from app.logger import get_logger
from app.storage import build_backend

log = get_logger("jobs")

_queue: asyncio.Queue[int] | None = None
_workers: list[asyncio.Task] = []


def _get_queue() -> asyncio.Queue:
    global _queue
    if _queue is None:
        _queue = asyncio.Queue()
    return _queue


def enqueue(job_id: int) -> None:
    _get_queue().put_nowait(job_id)


def _resolve_backend(storage_target_id: int | None):
    if storage_target_id:
        with get_session() as db:
            target = db.query(StorageTarget).get(storage_target_id)
            if target is None:
                raise ValueError(f"Storage target {storage_target_id} no longer exists")
            storage_type, config = target.type, target.config()
    else:
        storage_type, config = "local", {"base_dir": str(settings.default_download_dir)}
    return build_backend(storage_type, config)


async def _worker(worker_id: int) -> None:
    queue = _get_queue()
    log.info("Job worker %s started", worker_id)
    while True:
        job_id = await queue.get()
        try:
            with get_session() as db:
                job = db.query(Job).get(job_id)
                if job is None or job.status == "cancelled":
                    continue
                job_type = job.job_type
                storage_target_id = job.storage_target_id
            if job_type == "download":
                backend = _resolve_backend(storage_target_id)
                await run_download_job(job_id, backend)
            elif job_type == "export":
                backend = _resolve_backend(storage_target_id)
                await run_export_job(job_id, backend)
            elif job_type == "forward":
                await run_forward_job(job_id)
            else:
                log.error("Unknown job type for job %s", job_id)
        except Exception as e:  # noqa: BLE001
            log.exception("Worker error on job %s: %s", job_id, e)
            with get_session() as db:
                db.query(Job).filter_by(id=job_id).update({Job.status: "failed", Job.error: str(e)})
        finally:
            queue.task_done()


def start_workers() -> None:
    n = max(1, settings.max_concurrent_downloads)
    for i in range(n):
        _workers.append(asyncio.create_task(_worker(i)))
    log.info("Started %s job worker(s)", n)


def requeue_pending() -> None:
    """On startup, re-enqueue jobs that were left pending/running from a
    previous process (e.g. after a restart)."""
    with get_session() as db:
        stuck = db.query(Job).filter(Job.status.in_(["pending", "running"])).all()
        for job in stuck:
            job.status = "pending"
            enqueue(job.id)

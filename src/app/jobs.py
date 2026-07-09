"""In-process async job queues.

Downloads and forwards are split into two independent queues with separate
concurrency, because Telegram treats them very differently:

  - Downloading media is a read action. Telethon can genuinely have several
    file transfers in flight at once on the same client (this is how
    Telegram Desktop speeds up transfers), and there's no anti-spam
    heuristic watching "how many files did this account fetch". A small
    amount of download concurrency is safe and gives real throughput.

  - Forwarding is a write action Telegram's abuse detection specifically
    watches for bursty, automated behavior on. Running forward jobs in
    parallel doesn't parallelize the actual per-account rate limit — it's
    the same shared quota either way — it just means multiple workers race
    for that quota and hit FloodWaitError sooner, while looking more
    bot-like in the process. So the forward queue defaults to, and is
    strongly recommended to stay at, a single worker.

Export jobs share the download queue (they're a similar "read" workload).

A stale-job watchdog also runs alongside the workers (see start_watchdog):
if a job sits at "running" with no progress update for stale_job_minutes,
it's assumed dead — most commonly because the network dropped mid-job and
never recovered, leaving the worker task parked on a hung await — and is
auto-marked "failed" so Retry/Resume becomes available again without
needing a manual restart.
"""
from __future__ import annotations

import asyncio
import datetime

from app.config import settings
from app.database import get_session, Job, StorageTarget
from app.downloader import run_download_job
from app.exporter import run_export_job
from app.forwarder import run_forward_job
from app.logger import get_logger
from app.storage import build_backend

log = get_logger("jobs")

_download_queue: asyncio.Queue[int] | None = None
_forward_queue: asyncio.Queue[int] | None = None
_workers: list[asyncio.Task] = []
_watchdog_task: asyncio.Task | None = None


def _get_download_queue() -> asyncio.Queue:
    global _download_queue
    if _download_queue is None:
        _download_queue = asyncio.Queue()
    return _download_queue


def _get_forward_queue() -> asyncio.Queue:
    global _forward_queue
    if _forward_queue is None:
        _forward_queue = asyncio.Queue()
    return _forward_queue


def enqueue(job_id: int) -> None:
    with get_session() as db:
        job = db.query(Job).get(job_id)
        job_type = job.job_type if job else None
    if job_type == "forward":
        _get_forward_queue().put_nowait(job_id)
    else:
        _get_download_queue().put_nowait(job_id)


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


async def _run_job(job_id: int) -> None:
    try:
        with get_session() as db:
            job = db.query(Job).get(job_id)
            if job is None or job.status in ("cancelled", "paused"):
                return
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


async def _worker(queue: asyncio.Queue, label: str, worker_id: int) -> None:
    log.info("%s worker %s started", label, worker_id)
    while True:
        job_id = await queue.get()
        try:
            await _run_job(job_id)
        finally:
            queue.task_done()


def start_workers() -> None:
    n_download = max(1, settings.max_concurrent_downloads)
    n_forward = max(1, settings.max_concurrent_forwards)
    if n_forward > 1:
        log.warning(
            "MAX_CONCURRENT_FORWARDS=%s: forwarding in parallel doesn't increase your effective "
            "rate limit (it's one shared per-account quota either way) and raises the chance of "
            "hitting FloodWaitError sooner. 1 is recommended.", n_forward
        )

    dl_queue = _get_download_queue()
    for i in range(n_download):
        _workers.append(asyncio.create_task(_worker(dl_queue, "download/export", i)))

    fwd_queue = _get_forward_queue()
    for i in range(n_forward):
        _workers.append(asyncio.create_task(_worker(fwd_queue, "forward", i)))

    log.info("Started %s download/export worker(s), %s forward worker(s)", n_download, n_forward)


def requeue_pending() -> None:
    """On startup, re-enqueue jobs that were left pending/running from a
    previous process (e.g. after a restart)."""
    with get_session() as db:
        stuck = db.query(Job).filter(Job.status.in_(["pending", "running"])).all()
        job_ids = [j.id for j in stuck]
        for job in stuck:
            job.status = "pending"
    for job_id in job_ids:
        enqueue(job_id)


async def _watchdog_loop() -> None:
    check_interval = 60  # seconds
    while True:
        await asyncio.sleep(check_interval)
        try:
            cutoff = datetime.datetime.utcnow() - datetime.timedelta(minutes=settings.stale_job_minutes)
            with get_session() as db:
                stale = db.query(Job).filter(Job.status == "running", Job.updated_at < cutoff).all()
                for job in stale:
                    log.warning(
                        "Job %s (%s) stuck at 'running' with no progress since %s — marking failed "
                        "so it can be retried/resumed (likely a network interruption).",
                        job.id, job.job_type, job.updated_at,
                    )
                    job.status = "failed"
                    job.error = (
                        f"No progress for over {settings.stale_job_minutes} minute(s) — the job "
                        "likely stalled due to a network interruption. Marked failed automatically "
                        "so it can be retried; retrying resumes from where it left off."
                    )
        except Exception:  # noqa: BLE001
            log.exception("Stale-job watchdog check failed")


def start_watchdog() -> None:
    global _watchdog_task
    if _watchdog_task is None:
        _watchdog_task = asyncio.create_task(_watchdog_loop())
        log.info("Stale-job watchdog started (threshold: %s minute(s))", settings.stale_job_minutes)

"""Single-worker media download engine. Streams media directly into the
selected storage backend (local disk or a remote SFTP directory) — no
intermediate temp copy.

Resume-aware: each matched message gets a MediaItem row keyed by
(job_id, message_id). On any re-run of the same job (e.g. via the retry
endpoint), messages already marked "downloaded"/"verified" are skipped and
only pending/failed ones are re-attempted.
"""
from __future__ import annotations

import datetime

import hashlib

from app.database import get_session, Job, MediaItem
from app.filters import ALL_MEDIA_TYPES, iter_filtered_messages, media_type_of, parse_date
from app.logger import get_logger
from app.netutil import iter_with_timeout, with_timeout
from app.config import settings
from app.storage import StorageBackend
from app.telegram_client import manager as tg_manager

log = get_logger("downloader")

# Re-exported for backwards compatibility with modules importing from here
from app.filters import matches_media_types  # noqa: E402,F401


async def run_download_job(job_id: int, backend: StorageBackend) -> None:
    client = tg_manager.get_client()
    net_timeout = settings.network_call_timeout_seconds

    with get_session() as db:
        job = db.query(Job).get(job_id)
        job.status = "running"
        job.error = None
        opts = job.options()
        dialog_id = int(job.dialog_id)
        subfolder = opts.get("subfolder") or job.dialog_name or job.dialog_id
        subfolder = "".join(c for c in subfolder if c not in '\\/:*?"<>|').strip() or job.dialog_id
        # Existing progress from a prior (possibly failed) run of this job
        done_ids = {
            item.message_id for item in
            db.query(MediaItem).filter_by(job_id=job_id).filter(
                MediaItem.status.in_(["downloaded", "verified"])
            ).all()
        }

    media_types = opts.get("media_types") or ALL_MEDIA_TYPES
    limit = opts.get("limit")
    date_from = parse_date(opts.get("date_from"))
    date_to = parse_date(opts.get("date_to"))

    try:
        entity = await with_timeout(client.get_entity(dialog_id), net_timeout, "resolving dialog")
    except Exception as e:  # noqa: BLE001
        _fail_job(job_id, f"Could not resolve dialog: {e}")
        return

    # First pass: count matching messages for progress total
    total = 0
    try:
        async for _ in iter_with_timeout(
            iter_filtered_messages(client, entity, media_types, limit, date_from, date_to),
            net_timeout, "listing messages",
        ):
            total += 1
    except Exception as e:  # noqa: BLE001
        _fail_job(job_id, f"Could not list messages: {e}")
        return
    with get_session() as db:
        db.query(Job).filter_by(id=job_id).update({Job.total: total})

    processed = len(done_ids)
    with get_session() as db:
        db.query(Job).filter_by(id=job_id).update({Job.progress: processed, Job.updated_at: datetime.datetime.utcnow()})

    try:
        async for msg in iter_with_timeout(
            iter_filtered_messages(client, entity, media_types, limit, date_from, date_to),
            net_timeout, "listing messages",
        ):
            if msg.id in done_ids:
                continue  # already downloaded in a previous run — resume skips it

            with get_session() as db:
                current = db.query(Job).get(job_id)
                if current.status != "running":
                    # Cancelled, paused, or force-failed by the stale-job
                    # watchdog while we were mid-flight — stop cleanly
                    # either way; whatever set this status also decided
                    # what should happen next (cancel/pause/retry).
                    log.info("Job %s status changed to %s externally, stopping", job_id, current.status)
                    return

            filename = _build_filename(msg)
            relative_path = f"{subfolder}/{filename}"
            hasher = hashlib.sha256()
            size = 0
            try:
                with backend.open_write(relative_path) as fh:
                    async for chunk in iter_with_timeout(client.iter_download(msg.media), net_timeout, "downloading file"):
                        fh.write(chunk)
                        hasher.update(chunk)
                        size += len(chunk)
                status = "downloaded"
                error = None
            except Exception as e:  # noqa: BLE001
                status = "failed"
                error = str(e)
                log.warning("Failed to download message %s: %s", msg.id, e)

            with get_session() as db:
                existing = db.query(MediaItem).filter_by(job_id=job_id, message_id=msg.id).first()
                fields = dict(
                    filename=filename,
                    path=relative_path,
                    size=size,
                    checksum=hasher.hexdigest() if status == "downloaded" else None,
                    media_type=media_type_of(msg),
                    status=status,
                    error=error,
                )
                if existing:
                    for k, v in fields.items():
                        setattr(existing, k, v)
                else:
                    db.add(MediaItem(job_id=job_id, message_id=msg.id, **fields))
                processed += 1
                db.query(Job).filter_by(id=job_id).update({Job.progress: processed, Job.updated_at: datetime.datetime.utcnow()})

        with get_session() as db:
            failed_count = db.query(MediaItem).filter_by(job_id=job_id, status="failed").count()
            db.query(Job).filter_by(id=job_id).update({
                Job.status: "completed" if failed_count == 0 else "completed_with_errors",
                Job.output_path: backend.resolved_path(subfolder),
                Job.error: f"{failed_count} item(s) failed — use Retry to re-attempt them" if failed_count else None,
            })
        log.info("Job %s completed: %s items processed", job_id, processed)
    except Exception as e:  # noqa: BLE001
        _fail_job(job_id, str(e))
    finally:
        backend.close()


def _build_filename(msg) -> str:
    base = f"{msg.id}"
    ext = ""
    if msg.file and msg.file.ext:
        ext = msg.file.ext
    name = msg.file.name if msg.file and msg.file.name else None
    if name:
        return f"{base}_{name}"
    return f"{base}{ext}"


def _fail_job(job_id: int, error: str) -> None:
    with get_session() as db:
        db.query(Job).filter_by(id=job_id).update({Job.status: "failed", Job.error: error})
    log.error("Job %s failed: %s", job_id, error)

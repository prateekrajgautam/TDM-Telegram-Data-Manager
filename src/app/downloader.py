"""Single-worker media download engine. Streams media directly into the
selected storage backend (local disk or a remote SFTP directory) — no
intermediate temp copy.
"""
from __future__ import annotations

import hashlib

from app.database import get_session, Job, MediaItem
from app.logger import get_logger
from app.storage import StorageBackend
from app.telegram_client import manager as tg_manager

log = get_logger("downloader")

_MEDIA_TYPE_MAP = {
    "photo": lambda m: m.photo is not None,
    "video": lambda m: m.video is not None,
    "document": lambda m: m.document is not None and m.video is None and m.audio is None and m.voice is None,
    "audio": lambda m: m.audio is not None,
    "voice": lambda m: m.voice is not None,
}


def matches_media_types(message, media_types: list[str]) -> bool:
    if not message.media:
        return False
    for mt in media_types:
        check = _MEDIA_TYPE_MAP.get(mt)
        if check and check(message):
            return True
    return False


# Backwards-compatible alias
_matches_media_types = matches_media_types


async def run_download_job(job_id: int, backend: StorageBackend) -> None:
    client = tg_manager.get_client()

    with get_session() as db:
        job = db.query(Job).get(job_id)
        job.status = "running"
        opts = job.options()
        dialog_id = int(job.dialog_id)
        subfolder = opts.get("subfolder") or job.dialog_name or job.dialog_id
        subfolder = "".join(c for c in subfolder if c not in '\\/:*?"<>|').strip() or job.dialog_id

    media_types = opts.get("media_types", ["photo", "video", "document", "audio", "voice"])
    limit = opts.get("limit")
    min_id = opts.get("min_id", 0)
    max_id = opts.get("max_id", 0)

    try:
        entity = await client.get_entity(dialog_id)
    except Exception as e:  # noqa: BLE001
        _fail_job(job_id, f"Could not resolve dialog: {e}")
        return

    # First pass: count matching messages for progress total
    total = 0
    async for msg in client.iter_messages(entity, limit=limit, min_id=min_id, max_id=max_id):
        if _matches_media_types(msg, media_types):
            total += 1
    with get_session() as db:
        db.query(Job).filter_by(id=job_id).update({Job.total: total})

    downloaded = 0
    try:
        async for msg in client.iter_messages(entity, limit=limit, min_id=min_id, max_id=max_id):
            if not _matches_media_types(msg, media_types):
                continue

            with get_session() as db:
                current = db.query(Job).get(job_id)
                if current.status == "cancelled":
                    log.info("Job %s cancelled, stopping", job_id)
                    return

            filename = _build_filename(msg)
            relative_path = f"{subfolder}/{filename}"
            hasher = hashlib.sha256()
            size = 0
            try:
                with backend.open_write(relative_path) as fh:
                    async for chunk in client.iter_download(msg.media):
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
                db.add(MediaItem(
                    job_id=job_id,
                    message_id=msg.id,
                    filename=filename,
                    path=relative_path,
                    size=size,
                    checksum=hasher.hexdigest() if status == "downloaded" else None,
                    media_type=_media_type_of(msg),
                    status=status,
                    error=error,
                ))
                downloaded += 1
                db.query(Job).filter_by(id=job_id).update({Job.progress: downloaded})

        with get_session() as db:
            db.query(Job).filter_by(id=job_id).update({
                Job.status: "completed",
                Job.output_path: backend.resolved_path(subfolder),
            })
        log.info("Job %s completed: %s items", job_id, downloaded)
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


def _media_type_of(msg) -> str:
    for mt, check in _MEDIA_TYPE_MAP.items():
        if check(msg):
            return mt
    return "other"


def _fail_job(job_id: int, error: str) -> None:
    with get_session() as db:
        db.query(Job).filter_by(id=job_id).update({Job.status: "failed", Job.error: error})
    log.error("Job %s failed: %s", job_id, error)

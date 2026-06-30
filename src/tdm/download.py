"""
download.py
-----------
Core download engine (sections 8, 13, 14, 15 of the planning doc).

Single-worker, sequential implementation for Phase 1/2 — this is the
piece the project notes recommended building and testing first
(start with photos, confirm Ctrl+C resume works, then expand).
Concurrency (worker pool) is a Phase 2/3 follow-up once this path is solid.
"""

from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path

from telethon import TelegramClient
from telethon.errors import FloodWaitError
from telethon.tl.types import (
    DocumentAttributeAnimated,
    DocumentAttributeAudio,
    DocumentAttributeSticker,
    DocumentAttributeVideo,
)

from .config import Config
from .database import Database, Item

MEDIA_SUBFOLDERS = {
    "photo": "photos",
    "video": "videos",
    "audio": "audio",
    "voice": "voice",
    "document": "documents",
    "sticker": "stickers",
    "gif": "animations",
    "video_note": "videos",
    "other": "others",
}


def classify_media(message) -> str:
    """Map a Telethon message's media to one of TDM's media_type buckets."""
    if message.photo:
        return "photo"
    if message.voice:
        return "voice"
    if message.video_note:
        return "video_note"
    if message.gif:
        return "gif"
    if message.sticker:
        return "sticker"
    if message.video:
        return "video"
    if message.audio:
        return "audio"
    if message.document:
        return "document"
    return "other"


async def index_chat(client: TelegramClient, db: Database, chat_id: int,
                      limit: int | None = None) -> int:
    """Scan a chat's history and register media messages as pending items
    in the database (does not download anything). Returns count queued."""
    queued = 0
    async for message in client.iter_messages(chat_id, limit=limit):
        if not message.media:
            continue
        media_type = classify_media(message)
        file_id = getattr(getattr(message, "file", None), "id", None)
        item = Item(
            chat_id=chat_id,
            message_id=message.id,
            date=message.date.isoformat() if message.date else None,
            sender_id=message.sender_id,
            media_type=media_type,
            file_name=getattr(message.file, "name", None) if message.file else None,
            file_id=str(file_id) if file_id else None,
            file_size=getattr(message.file, "size", None) if message.file else None,
            caption=message.message or None,
        )
        db.add_item(item)
        queued += 1
    return queued


async def download_pending(
    client: TelegramClient,
    db: Database,
    cfg: Config,
    chat_id: int | None = None,
    progress_cb=None,
) -> dict:
    """Download all pending/failed items, respecting resume state,
    retry/backoff, FloodWait, and duplicate detection.

    progress_cb, if given, is called as progress_cb(item_row, status)
    so a Rich dashboard (ui.py) can render live progress.
    """
    results = {"downloaded": 0, "skipped": 0, "failed": 0}
    base_folder = Path(cfg.download_folder)

    for row in db.pending_items(chat_id=chat_id):
        item_id = row["id"]

        if row["file_id"] and db.is_duplicate_file_id(row["file_id"]):
            db.set_state(item_id, "skipped", "duplicate file_id")
            results["skipped"] += 1
            if progress_cb:
                progress_cb(row, "skipped")
            continue

        db.set_state(item_id, "downloading")
        subfolder = MEDIA_SUBFOLDERS.get(row["media_type"], "others")
        target_dir = base_folder / subfolder
        target_dir.mkdir(parents=True, exist_ok=True)

        success = await _download_with_retry(client, db, row, target_dir, cfg, progress_cb)
        if success:
            results["downloaded"] += 1
        else:
            results["failed"] += 1

    return results


async def _download_with_retry(client, db: Database, row, target_dir: Path,
                                cfg: Config, progress_cb) -> bool:
    item_id = row["id"]
    attempt = 0
    delay = 1.0

    while attempt <= cfg.retry_count:
        try:
            message = await client.get_messages(row["chat_id"], ids=row["message_id"])
            if message is None or not message.media:
                db.set_state(item_id, "failed", "message or media no longer exists")
                if progress_cb:
                    progress_cb(row, "failed")
                return False

            path = await client.download_media(message, file=str(target_dir) + "/")
            if path is None:
                raise RuntimeError("download_media returned None")

            sha256 = None
            if cfg.verification_enabled:
                sha256 = _sha256_of(Path(path))

            db.set_downloaded(item_id, path, sha256)
            if progress_cb:
                progress_cb(row, "downloaded")
            return True

        except FloodWaitError as e:
            if progress_cb:
                progress_cb(row, f"floodwait:{e.seconds}s")
            await asyncio.sleep(e.seconds)
            # FloodWait doesn't count as a normal retry attempt
            continue

        except Exception as e:  # noqa: BLE001 - log and retry per backoff policy
            attempt += 1
            db.increment_retry(item_id)
            db.set_state(item_id, "failed", str(e))
            if progress_cb:
                progress_cb(row, f"retry:{attempt}")
            if attempt > cfg.retry_count:
                return False
            await asyncio.sleep(delay)
            delay = min(delay * 2, 60)

    return False


def _sha256_of(path: Path, chunk_size: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            h.update(chunk)
    return h.hexdigest()

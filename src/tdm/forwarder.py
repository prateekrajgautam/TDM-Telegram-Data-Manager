"""Forwards messages from one chat/group/channel to another that you also
have access to. Telegram treats bulk forwarding as a rate-limited, abuse-
sensitive action, so this engine:
  - requires an explicit opt-in confirmation at job-creation time (enforced
    in the API layer, see routers/jobs.py)
  - paces requests with a small delay between forwards
  - honors FloodWaitError by sleeping the exact duration Telegram requests
  - never forwards from/to chats the account doesn't already have access to
    (Telethon's forward_messages requires this by construction)
"""
from __future__ import annotations

import asyncio

from telethon.errors import FloodWaitError

from app.database import get_session, Job
from app.downloader import matches_media_types
from app.logger import get_logger
from app.telegram_client import manager as tg_manager

log = get_logger("forwarder")

_MIN_DELAY_SECONDS = 2.0  # pacing between individual forwards


async def run_forward_job(job_id: int) -> None:
    client = tg_manager.get_client()

    with get_session() as db:
        job = db.query(Job).get(job_id)
        job.status = "running"
        opts = job.options()
        source_id = int(job.dialog_id)
        target_id = int(opts["target_dialog_id"])
        target_label = opts.get("target_dialog_name") or opts["target_dialog_id"]
        media_types = opts.get("media_types") or []
        limit = opts.get("limit")
        db.query(Job).filter_by(id=job_id).update({Job.output_path: f"forwarded to: {target_label}"})

    try:
        source = await client.get_entity(source_id)
        target = await client.get_entity(target_id)
    except Exception as e:  # noqa: BLE001
        _fail_job(job_id, f"Could not resolve source/target chat: {e}")
        return

    matched_ids: list[int] = []
    async for msg in client.iter_messages(source, limit=limit):
        if not media_types or matches_media_types(msg, media_types):
            matched_ids.append(msg.id)

    total = len(matched_ids)
    with get_session() as db:
        db.query(Job).filter_by(id=job_id).update({Job.total: total})

    if total == 0:
        with get_session() as db:
            db.query(Job).filter_by(id=job_id).update({Job.status: "completed"})
        return

    done = 0
    for msg_id in reversed(matched_ids):  # oldest first, preserves chronological order at target
        with get_session() as db:
            current = db.query(Job).get(job_id)
            if current.status == "cancelled":
                log.info("Forward job %s cancelled, stopping", job_id)
                return

        try:
            await client.forward_messages(target, msg_id, source)
        except FloodWaitError as e:
            log.warning("Flood wait on job %s: sleeping %ss", job_id, e.seconds)
            await asyncio.sleep(e.seconds)
            try:
                await client.forward_messages(target, msg_id, source)
            except Exception as e2:  # noqa: BLE001
                log.warning("Retry failed for message %s in job %s: %s", msg_id, job_id, e2)
        except Exception as e:  # noqa: BLE001
            log.warning("Failed to forward message %s in job %s: %s", msg_id, job_id, e)

        done += 1
        with get_session() as db:
            db.query(Job).filter_by(id=job_id).update({Job.progress: done})
        await asyncio.sleep(_MIN_DELAY_SECONDS)

    with get_session() as db:
        db.query(Job).filter_by(id=job_id).update({Job.status: "completed"})
    log.info("Forward job %s completed: %s/%s messages", job_id, done, total)


def _fail_job(job_id: int, error: str) -> None:
    with get_session() as db:
        db.query(Job).filter_by(id=job_id).update({Job.status: "failed", Job.error: error})
    log.error("Forward job %s failed: %s", job_id, error)

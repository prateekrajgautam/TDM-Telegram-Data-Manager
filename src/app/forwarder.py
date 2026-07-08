"""Forwards messages from one chat/group/channel to another that you also
have access to — a true server-to-server operation. Telethon's
forward_messages() calls Telegram's native MTProto forward; the message
moves directly between chats on Telegram's own servers. Nothing is
downloaded to, or stored on, this machine.

Because Telegram treats bulk forwarding as a rate-limited, abuse-sensitive
action, this engine:
  - requires an explicit opt-in confirmation at job-creation time (enforced
    in the API layer, see routers/jobs.py)
  - paces requests with a small delay between forwards
  - honors FloodWaitError by sleeping the exact duration Telegram requests

Resume-aware: each matched message gets a MediaItem row (reused as a
generic "transfer item" record) keyed by (job_id, message_id), so a retry
only re-attempts messages that previously failed.
"""
from __future__ import annotations

import asyncio

from telethon.errors import FloodWaitError

from app.database import get_session, Job, MediaItem
from app.filters import iter_filtered_messages, media_type_of, parse_date
from app.logger import get_logger
from app.telegram_client import manager as tg_manager

log = get_logger("forwarder")

_MIN_DELAY_SECONDS = 2.0  # pacing between individual forwards


async def run_forward_job(job_id: int) -> None:
    client = tg_manager.get_client()

    with get_session() as db:
        job = db.query(Job).get(job_id)
        job.status = "running"
        job.error = None
        opts = job.options()
        source_id = int(job.dialog_id)
        target_id = int(opts["target_dialog_id"])
        target_label = opts.get("target_dialog_name") or opts["target_dialog_id"]
        media_types = opts.get("media_types") or []
        limit = opts.get("limit")
        date_from = parse_date(opts.get("date_from"))
        date_to = parse_date(opts.get("date_to"))
        remove_forward_tag = opts.get("remove_forward_tag", True)
        db.query(Job).filter_by(id=job_id).update({Job.output_path: f"forwarded to: {target_label}"})
        done_ids = {
            item.message_id for item in
            db.query(MediaItem).filter_by(job_id=job_id, status="forwarded").all()
        }

    try:
        source = await client.get_entity(source_id)
        target = await client.get_entity(target_id)
    except Exception as e:  # noqa: BLE001
        _fail_job(job_id, f"Could not resolve source/target chat: {e}")
        return

    matched: list = []
    async for msg in iter_filtered_messages(client, source, media_types, limit, date_from, date_to):
        matched.append(msg)

    total = len(matched)
    with get_session() as db:
        db.query(Job).filter_by(id=job_id).update({Job.total: total})

    if total == 0:
        with get_session() as db:
            db.query(Job).filter_by(id=job_id).update({Job.status: "completed"})
        return

    done = len(done_ids)
    with get_session() as db:
        db.query(Job).filter_by(id=job_id).update({Job.progress: done})

    for msg in reversed(matched):  # oldest first, preserves chronological order at target
        if msg.id in done_ids:
            continue  # already forwarded in a previous run — resume skips it

        with get_session() as db:
            current = db.query(Job).get(job_id)
            if current.status == "cancelled":
                log.info("Forward job %s cancelled, stopping", job_id)
                return

        status, error = "forwarded", None
        try:
            await client.forward_messages(target, msg.id, source, drop_author=remove_forward_tag)
        except FloodWaitError as e:
            log.warning("Flood wait on job %s: sleeping %ss", job_id, e.seconds)
            await asyncio.sleep(e.seconds)
            try:
                await client.forward_messages(target, msg.id, source, drop_author=remove_forward_tag)
            except Exception as e2:  # noqa: BLE001
                status, error = "failed", str(e2)
                log.warning("Retry failed for message %s in job %s: %s", msg.id, job_id, e2)
        except Exception as e:  # noqa: BLE001
            status, error = "failed", str(e)
            log.warning("Failed to forward message %s in job %s: %s", msg.id, job_id, e)

        with get_session() as db:
            existing = db.query(MediaItem).filter_by(job_id=job_id, message_id=msg.id).first()
            if existing:
                existing.status, existing.error, existing.media_type = status, error, media_type_of(msg)
            else:
                db.add(MediaItem(job_id=job_id, message_id=msg.id, status=status, error=error,
                                  media_type=media_type_of(msg)))
            done += 1
            db.query(Job).filter_by(id=job_id).update({Job.progress: done})
        await asyncio.sleep(_MIN_DELAY_SECONDS)

    with get_session() as db:
        failed_count = db.query(MediaItem).filter_by(job_id=job_id, status="failed").count()
        db.query(Job).filter_by(id=job_id).update({
            Job.status: "completed" if failed_count == 0 else "completed_with_errors",
            Job.error: f"{failed_count} message(s) failed to forward — use Retry to re-attempt them" if failed_count else None,
        })
    log.info("Forward job %s completed: %s/%s messages", job_id, done, total)


def _fail_job(job_id: int, error: str) -> None:
    with get_session() as db:
        db.query(Job).filter_by(id=job_id).update({Job.status: "failed", Job.error: error})
    log.error("Forward job %s failed: %s", job_id, error)

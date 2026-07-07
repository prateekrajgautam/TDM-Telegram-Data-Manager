"""Exports dialog message metadata to JSON, CSV, or a browsable HTML file,
streamed directly into the selected storage backend.
"""
from __future__ import annotations

import csv
import io
import json

from app.database import get_session, Job
from app.logger import get_logger
from app.storage import StorageBackend
from app.telegram_client import manager as tg_manager

log = get_logger("exporter")


def _serialize_message(msg) -> dict:
    return {
        "id": msg.id,
        "date": msg.date.isoformat() if msg.date else None,
        "sender_id": msg.sender_id,
        "text": msg.message,
        "has_media": bool(msg.media),
        "media_type": type(msg.media).__name__ if msg.media else None,
        "views": getattr(msg, "views", None),
        "reply_to_msg_id": msg.reply_to_msg_id,
    }


async def run_export_job(job_id: int, backend: StorageBackend) -> None:
    client = tg_manager.get_client()
    with get_session() as db:
        job = db.query(Job).get(job_id)
        job.status = "running"
        opts = job.options()
        dialog_id = int(job.dialog_id)
        fmt = opts.get("format", "json")
        limit = opts.get("limit")
        dialog_name = job.dialog_name or job.dialog_id

    safe_name = "".join(c for c in dialog_name if c not in '\\/:*?"<>|').strip() or job.dialog_id

    try:
        entity = await client.get_entity(dialog_id)
    except Exception as e:  # noqa: BLE001
        with get_session() as db:
            db.query(Job).filter_by(id=job_id).update({Job.status: "failed", Job.error: str(e)})
        return

    messages = []
    async for msg in client.iter_messages(entity, limit=limit):
        messages.append(_serialize_message(msg))
        with get_session() as db:
            db.query(Job).filter_by(id=job_id).update({Job.progress: len(messages)})

    with get_session() as db:
        db.query(Job).filter_by(id=job_id).update({Job.total: len(messages)})

    ext = {"json": "json", "csv": "csv", "html": "html"}.get(fmt, "json")
    relative_path = f"exports/{safe_name}.{ext}"

    buf = io.StringIO()
    if fmt == "json":
        buf.write(json.dumps(messages, indent=2, ensure_ascii=False))
    elif fmt == "csv":
        writer = csv.DictWriter(buf, fieldnames=list(messages[0].keys()) if messages else
                                 ["id", "date", "sender_id", "text", "has_media", "media_type", "views", "reply_to_msg_id"])
        writer.writeheader()
        writer.writerows(messages)
    else:  # html
        buf.write(f"<html><head><meta charset='utf-8'><title>{safe_name}</title>")
        buf.write("<style>body{font-family:sans-serif;max-width:800px;margin:2rem auto}"
                   ".msg{border-bottom:1px solid #eee;padding:.5rem 0}.meta{color:#888;font-size:.8em}</style>")
        buf.write(f"</head><body><h1>{safe_name}</h1>")
        for m in messages:
            buf.write(f"<div class='msg'><div class='meta'>#{m['id']} — {m['date']}"
                       f"{' • media: ' + m['media_type'] if m['media_type'] else ''}</div>"
                       f"<div>{(m['text'] or '').replace(chr(10), '<br>')}</div></div>")
        buf.write("</body></html>")

    with backend.open_write(relative_path) as fh:
        fh.write(buf.getvalue().encode("utf-8"))

    with get_session() as db:
        db.query(Job).filter_by(id=job_id).update({
            Job.status: "completed",
            Job.output_path: backend.resolved_path(relative_path),
        })
    backend.close()
    log.info("Export job %s completed: %s messages", job_id, len(messages))

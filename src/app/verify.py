"""Integrity verification for downloaded media: recomputes checksums and
compares against the value recorded at download time.
"""
from __future__ import annotations

import hashlib

from app.database import get_session, MediaItem, Job
from app.logger import get_logger
from app.storage import StorageBackend

log = get_logger("verify")


def verify_job(job_id: int, backend: StorageBackend) -> dict:
    with get_session() as db:
        items = db.query(MediaItem).filter_by(job_id=job_id, status="downloaded").all()
        results = {"checked": 0, "ok": 0, "mismatched": 0, "missing": 0}
        for item in items:
            results["checked"] += 1
            if not backend.exists(item.path):
                item.status = "failed"
                item.error = "file missing"
                results["missing"] += 1
                continue
            hasher = hashlib.sha256()
            with backend.open_read(item.path) as fh:
                for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                    hasher.update(chunk)
            digest = hasher.hexdigest()
            if digest == item.checksum:
                item.status = "verified"
                results["ok"] += 1
            else:
                item.status = "failed"
                item.error = "checksum mismatch"
                results["mismatched"] += 1
    log.info("Verified job %s: %s", job_id, results)
    return results

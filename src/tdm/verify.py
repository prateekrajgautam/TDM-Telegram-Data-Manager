"""
verify.py
---------
Verification command (sections 12 & 21): checks that downloaded files
still exist on disk, match their recorded size, and optionally checks
sha256 against what was recorded at download time.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from .database import Database


def verify_all(db: Database) -> dict:
    """Return a report of missing/corrupted/ok files among downloaded items."""
    report = {"ok": 0, "missing": 0, "size_mismatch": 0, "hash_mismatch": 0}

    with db.cursor() as cur:
        cur.execute("SELECT * FROM items WHERE state='downloaded'")
        rows = cur.fetchall()

    for row in rows:
        path = Path(row["download_path"]) if row["download_path"] else None
        if not path or not path.exists():
            report["missing"] += 1
            continue

        if row["file_size"] and path.stat().st_size != row["file_size"]:
            report["size_mismatch"] += 1
            continue

        if row["sha256"]:
            actual = _sha256_of(path)
            if actual != row["sha256"]:
                report["hash_mismatch"] += 1
                continue

        report["ok"] += 1

    return report


def _sha256_of(path: Path, chunk_size: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            h.update(chunk)
    return h.hexdigest()

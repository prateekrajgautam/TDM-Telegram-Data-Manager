"""
exporter.py
-----------
Exports item metadata to CSV / JSON (section 11, 20). SQLite export is
just db.path itself - already in that format. HTML report is a Phase 4
follow-up once stats() output is finalized.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

from .database import Database

EXPORT_FIELDS = [
    "id", "chat_id", "message_id", "date", "sender_id", "media_type",
    "file_name", "file_id", "file_size", "sha256", "caption",
    "download_path", "state", "forward_status",
]


def export_csv(db: Database, out_path: str | Path) -> int:
    with db.cursor() as cur:
        cur.execute(f"SELECT {', '.join(EXPORT_FIELDS)} FROM items")
        rows = cur.fetchall()

    out_path = Path(out_path)
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(EXPORT_FIELDS)
        for row in rows:
            writer.writerow([row[field] for field in EXPORT_FIELDS])
    return len(rows)


def export_json(db: Database, out_path: str | Path) -> int:
    with db.cursor() as cur:
        cur.execute(f"SELECT {', '.join(EXPORT_FIELDS)} FROM items")
        rows = cur.fetchall()

    data = [{field: row[field] for field in EXPORT_FIELDS} for row in rows]
    out_path = Path(out_path)
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=str)
    return len(data)

"""
database.py
-----------
SQLite-backed state store. This is the backbone of the resume engine
(section 7), metadata export (section 11), verification (section 12),
and duplicate detection (section 13) from the planning doc.

Every other module should read/write through this module rather than
touching SQLite directly, so the schema can evolve in one place.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Optional

SCHEMA = """
CREATE TABLE IF NOT EXISTS chats (
    chat_id     INTEGER PRIMARY KEY,
    title       TEXT,
    type        TEXT,           -- 'channel' | 'group' | 'private'
    last_synced TEXT
);

CREATE TABLE IF NOT EXISTS items (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id         INTEGER NOT NULL,
    message_id      INTEGER NOT NULL,
    date            TEXT,
    sender_id       INTEGER,
    media_type      TEXT,       -- photo|video|audio|voice|document|gif|video_note|sticker
    file_name       TEXT,
    file_id         TEXT,       -- Telegram's unique file identifier (dedup key)
    file_size       INTEGER,
    sha256          TEXT,
    caption         TEXT,
    download_path   TEXT,
    state           TEXT NOT NULL DEFAULT 'pending',
        -- pending|downloading|downloaded|forwarding|completed|failed|skipped
    fail_reason     TEXT,
    retry_count     INTEGER NOT NULL DEFAULT 0,
    forward_status  TEXT,       -- null|pending|done|failed
    created_at      TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at      TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(chat_id, message_id)
);

CREATE INDEX IF NOT EXISTS idx_items_state ON items(state);
CREATE INDEX IF NOT EXISTS idx_items_file_id ON items(file_id);
CREATE INDEX IF NOT EXISTS idx_items_chat ON items(chat_id);
"""


@dataclass
class Item:
    chat_id: int
    message_id: int
    date: Optional[str] = None
    sender_id: Optional[int] = None
    media_type: Optional[str] = None
    file_name: Optional[str] = None
    file_id: Optional[str] = None
    file_size: Optional[int] = None
    caption: Optional[str] = None
    state: str = "pending"


class Database:
    """Thin wrapper around sqlite3 with the TDM schema applied."""

    def __init__(self, path: str | Path = "tdm.db") -> None:
        self.path = Path(path)
        self._conn = sqlite3.connect(self.path)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    @contextmanager
    def cursor(self) -> Iterator[sqlite3.Cursor]:
        cur = self._conn.cursor()
        try:
            yield cur
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise
        finally:
            cur.close()

    def close(self) -> None:
        self._conn.close()

    # -- chats -----------------------------------------------------------

    def upsert_chat(self, chat_id: int, title: str, chat_type: str) -> None:
        with self.cursor() as cur:
            cur.execute(
                """INSERT INTO chats (chat_id, title, type, last_synced)
                   VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                   ON CONFLICT(chat_id) DO UPDATE SET
                     title=excluded.title, type=excluded.type,
                     last_synced=CURRENT_TIMESTAMP""",
                (chat_id, title, chat_type),
            )

    # -- items (resume engine) -------------------------------------------

    def add_item(self, item: Item) -> int:
        """Insert a pending item. Returns row id. No-ops on duplicates."""
        with self.cursor() as cur:
            cur.execute(
                """INSERT OR IGNORE INTO items
                   (chat_id, message_id, date, sender_id, media_type,
                    file_name, file_id, file_size, caption, state)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    item.chat_id, item.message_id, item.date, item.sender_id,
                    item.media_type, item.file_name, item.file_id,
                    item.file_size, item.caption, item.state,
                ),
            )
            return cur.lastrowid

    def set_state(self, item_id: int, state: str, fail_reason: str | None = None) -> None:
        with self.cursor() as cur:
            cur.execute(
                """UPDATE items SET state=?, fail_reason=?, updated_at=CURRENT_TIMESTAMP
                   WHERE id=?""",
                (state, fail_reason, item_id),
            )

    def set_downloaded(self, item_id: int, download_path: str, sha256: str | None = None) -> None:
        with self.cursor() as cur:
            cur.execute(
                """UPDATE items SET state='downloaded', download_path=?, sha256=?,
                   updated_at=CURRENT_TIMESTAMP WHERE id=?""",
                (download_path, sha256, item_id),
            )

    def increment_retry(self, item_id: int) -> int:
        with self.cursor() as cur:
            cur.execute(
                "UPDATE items SET retry_count = retry_count + 1 WHERE id=?",
                (item_id,),
            )
            cur.execute("SELECT retry_count FROM items WHERE id=?", (item_id,))
            row = cur.fetchone()
            return row["retry_count"] if row else 0

    def pending_items(self, chat_id: int | None = None) -> list[sqlite3.Row]:
        with self.cursor() as cur:
            if chat_id is not None:
                cur.execute(
                    "SELECT * FROM items WHERE chat_id=? AND state IN ('pending','failed') ORDER BY message_id",
                    (chat_id,),
                )
            else:
                cur.execute(
                    "SELECT * FROM items WHERE state IN ('pending','failed') ORDER BY chat_id, message_id"
                )
            return cur.fetchall()

    def is_duplicate_file_id(self, file_id: str) -> bool:
        with self.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM items WHERE file_id=? AND state='downloaded' LIMIT 1",
                (file_id,),
            )
            return cur.fetchone() is not None

    def stats(self) -> dict:
        with self.cursor() as cur:
            cur.execute("SELECT state, COUNT(*) AS n FROM items GROUP BY state")
            rows = {row["state"]: row["n"] for row in cur.fetchall()}
            cur.execute("SELECT COALESCE(SUM(file_size),0) AS total FROM items WHERE state='downloaded'")
            total_size = cur.fetchone()["total"]
            return {"by_state": rows, "total_downloaded_bytes": total_size}

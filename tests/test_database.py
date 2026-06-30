"""
test_database.py
-----------------
Tests for the resume engine / metadata store. Run with: pytest
"""

import os
import tempfile

import pytest

from tdm.database import Database, Item


@pytest.fixture
def db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    database = Database(path)
    yield database
    database.close()
    os.unlink(path)


def test_add_item_and_pending(db):
    item = Item(chat_id=1, message_id=100, media_type="photo", file_id="abc")
    db.add_item(item)
    pending = db.pending_items(chat_id=1)
    assert len(pending) == 1
    assert pending[0]["state"] == "pending"


def test_duplicate_message_is_ignored(db):
    item = Item(chat_id=1, message_id=100, media_type="photo", file_id="abc")
    db.add_item(item)
    db.add_item(item)  # same chat_id+message_id
    pending = db.pending_items(chat_id=1)
    assert len(pending) == 1


def test_set_downloaded_and_dedup_by_file_id(db):
    item = Item(chat_id=1, message_id=1, media_type="photo", file_id="dup1")
    item_id = db.add_item(item)
    db.set_downloaded(item_id, "/tmp/fake.jpg", sha256="deadbeef")
    assert db.is_duplicate_file_id("dup1") is True
    assert db.is_duplicate_file_id("not_present") is False


def test_retry_increment(db):
    item = Item(chat_id=1, message_id=2, media_type="video")
    item_id = db.add_item(item)
    assert db.increment_retry(item_id) == 1
    assert db.increment_retry(item_id) == 2


def test_stats(db):
    item = Item(chat_id=1, message_id=3, media_type="photo", file_size=1024)
    item_id = db.add_item(item)
    db.set_downloaded(item_id, "/tmp/x.jpg")
    stats = db.stats()
    assert stats["by_state"]["downloaded"] == 1
    assert stats["total_downloaded_bytes"] == 1024

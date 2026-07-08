"""Shared message-filtering helpers used by both the download and forward
engines: media type matching, date-range ("period") filtering, and a single
iterator both engines drive off of so filter semantics never drift apart.
"""
from __future__ import annotations

import datetime

MEDIA_TYPE_CHECKS = {
    "photo": lambda m: m.photo is not None,
    "video": lambda m: m.video is not None,
    "document": lambda m: m.document is not None and m.video is None and m.audio is None and m.voice is None,
    "audio": lambda m: m.audio is not None,
    "voice": lambda m: m.voice is not None,
}

ALL_MEDIA_TYPES = list(MEDIA_TYPE_CHECKS.keys())


def matches_media_types(message, media_types: list[str] | None) -> bool:
    """If media_types is falsy, every message matches (used by "forward
    everything, including text"). Otherwise the message must carry media of
    one of the listed types."""
    if not media_types:
        return True
    if not message.media:
        return False
    for mt in media_types:
        check = MEDIA_TYPE_CHECKS.get(mt)
        if check and check(message):
            return True
    return False


def media_type_of(msg) -> str | None:
    for mt, check in MEDIA_TYPE_CHECKS.items():
        if check(msg):
            return mt
    return None


def parse_date(value: str | None) -> datetime.datetime | None:
    if not value:
        return None
    d = datetime.datetime.fromisoformat(value)
    if d.tzinfo is None:
        d = d.replace(tzinfo=datetime.timezone.utc)
    return d


async def iter_filtered_messages(client, entity, media_types=None, limit=None,
                                  date_from=None, date_to=None):
    """Yields messages matching the media-type and date-range filters.
    Telethon's default iteration order is newest-first, so once a message
    falls before date_from we can stop early rather than scanning the whole
    history."""
    count = 0
    async for msg in client.iter_messages(entity, offset_date=date_to):
        if date_from and msg.date and msg.date < date_from:
            break
        if not matches_media_types(msg, media_types):
            continue
        yield msg
        count += 1
        if limit and count >= limit:
            break

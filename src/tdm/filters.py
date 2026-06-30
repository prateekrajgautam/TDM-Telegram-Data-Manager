"""
filters.py
----------
Phase 3 module: date range, media type, sender, message id, file size,
filename/caption regex filters (section 10 of the planning doc).

Implemented as simple predicate builders that return a function
Item -> bool, so they can be composed and applied when querying
db.pending_items() or when indexing a chat.
"""

from __future__ import annotations

from datetime import datetime
from typing import Callable, Optional

Predicate = Callable[[dict], bool]


def date_range(from_date: Optional[str] = None, to_date: Optional[str] = None) -> Predicate:
    f = datetime.fromisoformat(from_date) if from_date else None
    t = datetime.fromisoformat(to_date) if to_date else None

    def check(item: dict) -> bool:
        if not item.get("date"):
            return True
        d = datetime.fromisoformat(item["date"])
        if f and d < f:
            return False
        if t and d > t:
            return False
        return True

    return check


def media_type_in(types: list[str]) -> Predicate:
    return lambda item: item.get("media_type") in types


def file_size_range(min_bytes: Optional[int] = None, max_bytes: Optional[int] = None) -> Predicate:
    def check(item: dict) -> bool:
        size = item.get("file_size") or 0
        if min_bytes and size < min_bytes:
            return False
        if max_bytes and size > max_bytes:
            return False
        return True

    return check


def combine(*predicates: Predicate) -> Predicate:
    return lambda item: all(p(item) for p in predicates)

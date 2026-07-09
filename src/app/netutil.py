"""Network resilience helpers.

Telethon (like most async network clients) can, under a broken or
half-open connection, leave an `await` hanging indefinitely instead of
raising — there's no timeout by default on a single RPC call or a single
downloaded chunk. That's the failure mode behind a job showing "running"
forever after a real network interruption: the worker task isn't dead, it's
just parked on an await that will never resolve on its own.

These helpers put a hard ceiling on any single network step. When a step
times out, it raises TimeoutError, which the existing per-item try/except
blocks in downloader.py/forwarder.py catch (marking that item failed and
moving on), or which bubbles up to jobs.py's outer handler (marking the
whole job failed, so Retry/Resume becomes available) — rather than the
job silently hanging with no way to recover short of a manual restart.
"""
from __future__ import annotations

import asyncio
from typing import AsyncIterator, TypeVar

T = TypeVar("T")


async def with_timeout(coro, timeout: float, what: str = "operation"):
    try:
        return await asyncio.wait_for(coro, timeout=timeout)
    except asyncio.TimeoutError:
        raise TimeoutError(f"{what} timed out after {timeout:.0f}s — likely a network interruption")


async def iter_with_timeout(aiter, timeout: float, what: str = "stream read") -> AsyncIterator[T]:
    """Wraps an async iterator so each individual `__anext__()` step has its
    own timeout, rather than the whole iteration sharing one deadline. A
    slow-but-alive multi-hour download won't be killed by this; a step that
    genuinely never returns (dead connection) will be."""
    it = aiter.__aiter__()
    while True:
        try:
            item = await asyncio.wait_for(it.__anext__(), timeout=timeout)
        except StopAsyncIteration:
            return
        except asyncio.TimeoutError:
            raise TimeoutError(f"{what} timed out after {timeout:.0f}s — likely a network interruption")
        yield item

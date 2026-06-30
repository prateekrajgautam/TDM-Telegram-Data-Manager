"""
forward.py
----------
Phase 3 module (not yet implemented in this scaffold).

Forwarding is the riskiest feature ToS-wise even though it only uses
official APIs, since bulk-forwarding into a new group can resemble
scraping/redistribution depending on source content. Guardrails to
build in here:
  - require explicit --confirm flag / interactive confirmation per run
  - default forward_delay_seconds from config (conservative pacing)
  - never forward without the user targeting a specific destination chat
  - log every forward action to logs/backup.log for auditability
"""

from __future__ import annotations


async def forward_pending(*args, **kwargs):
    raise NotImplementedError(
        "Forward engine is a Phase 3 feature - not yet implemented. "
        "See project notes: build download engine first, add forwarding "
        "with opt-in guardrails once download/resume is solid."
    )

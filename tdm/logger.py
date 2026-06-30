"""
logger.py
---------
Sets up the three log files described in section 17 of the planning doc:
  logs/backup.log   - everything (info+)
  logs/error.log    - errors and failures only
  logs/summary.log  - high level run summaries (one line per run)

Also wires up Rich for pretty console output.
"""

from __future__ import annotations

import logging
from pathlib import Path

from rich.logging import RichHandler

_LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"


def setup_logging(log_folder: str = "logs", console: bool = True) -> logging.Logger:
    folder = Path(log_folder)
    folder.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("tdm")
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()

    formatter = logging.Formatter(_LOG_FORMAT)

    backup_handler = logging.FileHandler(folder / "backup.log", encoding="utf-8")
    backup_handler.setLevel(logging.INFO)
    backup_handler.setFormatter(formatter)
    logger.addHandler(backup_handler)

    error_handler = logging.FileHandler(folder / "error.log", encoding="utf-8")
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(formatter)
    logger.addHandler(error_handler)

    if console:
        rich_handler = RichHandler(rich_tracebacks=True, show_path=False)
        rich_handler.setLevel(logging.INFO)
        logger.addHandler(rich_handler)

    return logger


def log_summary(log_folder: str, message: str) -> None:
    """Append a one-line summary entry, e.g. after a backup run finishes."""
    folder = Path(log_folder)
    folder.mkdir(parents=True, exist_ok=True)
    with (folder / "summary.log").open("a", encoding="utf-8") as f:
        from datetime import datetime
        f.write(f"{datetime.now().isoformat(timespec='seconds')} | {message}\n")

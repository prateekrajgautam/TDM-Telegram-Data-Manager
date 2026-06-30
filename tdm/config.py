"""
config.py
---------
Loads, validates, and saves TDM's configuration (config.json).

Design notes:
- Uses pydantic for validation so a malformed config.json fails loudly
  with a clear error instead of crashing deep inside the download engine.
- A default config is created on first run if none exists.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field

DEFAULT_CONFIG_PATH = Path("config.json")


class Config(BaseModel):
    download_folder: str = "downloads"
    workers: int = Field(default=4, ge=1, le=32)
    retry_count: int = Field(default=5, ge=0, le=20)
    resume_enabled: bool = True
    save_metadata: bool = True
    verification_enabled: bool = True
    theme: str = "default"

    # Telegram API credentials (api_id/api_hash come from my.telegram.org)
    api_id: int | None = None
    api_hash: str | None = None
    session_name: str = "telegram"

    # Forwarding is opt-in and conservative by default (see project notes
    # on ToS risk for bulk forwarding).
    forward_delay_seconds: float = 3.0

    log_folder: str = "logs"
    db_path: str = "tdm.db"


def load_config(path: Path = DEFAULT_CONFIG_PATH) -> Config:
    """Load config.json, creating a default one if it doesn't exist."""
    if not path.exists():
        cfg = Config()
        save_config(cfg, path)
        return cfg

    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    return Config(**data)


def save_config(cfg: Config, path: Path = DEFAULT_CONFIG_PATH) -> None:
    with path.open("w", encoding="utf-8") as f:
        json.dump(cfg.model_dump(), f, indent=2)

"""Application configuration via environment variables (.env supported)."""
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Telegram API credentials — obtain from https://my.telegram.org
    telegram_api_id: int = 0
    telegram_api_hash: str = ""

    # Web server
    host: str = "0.0.0.0"
    port: int = 8000
    secret_key: str = "change-me-in-production"

    # Storage paths (inside the container). Map these to host volumes.
    data_dir: Path = Path("/app/data")
    default_download_dir: Path = Path("/app/downloads")

    # Job engine — downloads/exports and forwards are separate pools (see
    # jobs.py docstring for why forwarding stays low by default).
    max_concurrent_downloads: int = 2
    max_concurrent_forwards: int = 1

    # Fault tolerance: a single network step (one RPC call, one downloaded
    # chunk) waits at most this long before being treated as a dead
    # connection rather than hanging forever.
    network_call_timeout_seconds: int = 30

    # Watchdog: a job stuck at "running" with no progress update in this
    # many minutes is assumed dead (e.g. the network dropped mid-job and
    # never recovered) and is auto-marked "failed" so Retry/Resume works
    # again, instead of sitting stuck until someone manually intervenes.
    stale_job_minutes: int = 5

    # Bump this on every meaningful change — shown in logs and /health so you
    # can confirm a deployment is actually running the code you think it is.
    app_version: str = "0.3.0"

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.data_dir / 'tdm.db'}"

    @property
    def sessions_dir(self) -> Path:
        d = self.data_dir / "sessions"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.default_download_dir.mkdir(parents=True, exist_ok=True)
        self.sessions_dir


settings = Settings()

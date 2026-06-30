"""
auth.py
-------
Handles login/logout against Telegram's MTProto API via Telethon.

First run prompts for:
  - API ID / API Hash (from https://my.telegram.org)
  - phone number, OTP, optional 2FA password
and persists a .session file so subsequent runs are silent.

NOTE: the .session file is a bearer credential for the Telegram account.
Treat it like a password - never commit it, and consider chmod 600 on
non-Windows systems (done automatically below where possible).
"""

from __future__ import annotations

import os
import stat
from pathlib import Path

from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError

from .config import Config


async def get_client(cfg: Config) -> TelegramClient:
    """Return a connected, authorized TelegramClient, prompting for
    credentials on first run if needed."""
    if not cfg.api_id or not cfg.api_hash:
        raise RuntimeError(
            "api_id / api_hash not set in config.json. "
            "Get them from https://my.telegram.org and add them to config.json."
        )

    client = TelegramClient(cfg.session_name, cfg.api_id, cfg.api_hash)
    await client.connect()

    if not await client.is_user_authorized():
        await _interactive_login(client)

    _secure_session_file(cfg.session_name)
    return client


async def _interactive_login(client: TelegramClient) -> None:
    phone = input("Phone number (with country code, e.g. +1234567890): ").strip()
    await client.send_code_request(phone)
    code = input("OTP code received: ").strip()
    try:
        await client.sign_in(phone, code)
    except SessionPasswordNeededError:
        password = input("Two-factor password: ").strip()
        await client.sign_in(password=password)


def _secure_session_file(session_name: str) -> None:
    path = Path(f"{session_name}.session")
    if path.exists() and os.name != "nt":
        path.chmod(stat.S_IRUSR | stat.S_IWUSR)  # 0600


async def logout(cfg: Config) -> None:
    """Log out and remove the session file."""
    client = TelegramClient(cfg.session_name, cfg.api_id, cfg.api_hash)
    await client.connect()
    if await client.is_user_authorized():
        await client.log_out()
    await client.disconnect()

    session_path = Path(f"{cfg.session_name}.session")
    if session_path.exists():
        session_path.unlink()

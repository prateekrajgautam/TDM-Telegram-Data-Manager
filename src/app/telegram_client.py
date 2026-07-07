"""Wraps Telethon: login flow (phone -> code -> 2FA password), session
persistence to disk, and a single shared connected client for the active
account.
"""
from __future__ import annotations

from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError

from app.config import settings
from app.database import get_session, Account
from app.logger import get_logger

log = get_logger("telegram_client")


class TelegramManager:
    def __init__(self):
        self._pending: dict[str, TelegramClient] = {}
        self._active_client: TelegramClient | None = None
        self._active_phone: str | None = None

    def _session_path(self, phone: str) -> str:
        safe = phone.replace("+", "").replace(" ", "")
        return str(settings.sessions_dir / f"session_{safe}")

    async def send_code(self, phone: str) -> None:
        client = TelegramClient(self._session_path(phone), settings.telegram_api_id, settings.telegram_api_hash)
        await client.connect()
        await client.send_code_request(phone)
        self._pending[phone] = client

    async def submit_code(self, phone: str, code: str) -> str:
        """Returns 'ok' or 'password_needed'."""
        client = self._pending.get(phone)
        if client is None:
            raise RuntimeError("No pending login for this phone. Request a code first.")
        try:
            await client.sign_in(phone=phone, code=code)
        except SessionPasswordNeededError:
            return "password_needed"
        await self._finalize_login(phone, client)
        return "ok"

    async def submit_password(self, phone: str, password: str) -> None:
        client = self._pending.get(phone)
        if client is None:
            raise RuntimeError("No pending login for this phone.")
        await client.sign_in(password=password)
        await self._finalize_login(phone, client)

    async def _finalize_login(self, phone: str, client: TelegramClient) -> None:
        me = await client.get_me()
        with get_session() as db:
            db.query(Account).update({Account.is_active: False})
            existing = db.query(Account).filter_by(phone=phone).first()
            if existing:
                existing.is_active = True
                existing.first_name = me.first_name
                existing.username = me.username
            else:
                db.add(Account(
                    phone=phone,
                    session_name=self._session_path(phone),
                    first_name=me.first_name,
                    username=me.username,
                    is_active=True,
                ))
        self._active_client = client
        self._active_phone = phone
        self._pending.pop(phone, None)
        log.info("Logged in as %s (%s)", me.first_name, phone)

    async def restore_active_session(self) -> bool:
        with get_session() as db:
            account = db.query(Account).filter_by(is_active=True).first()
            if not account:
                return False
            phone = account.phone
            session_name = account.session_name
        client = TelegramClient(session_name, settings.telegram_api_id, settings.telegram_api_hash)
        await client.connect()
        if not await client.is_user_authorized():
            return False
        self._active_client = client
        self._active_phone = phone
        log.info("Restored session for %s", phone)
        return True

    async def logout(self) -> None:
        if self._active_client:
            with get_session() as db:
                db.query(Account).update({Account.is_active: False})
            await self._active_client.log_out()
            self._active_client = None
            self._active_phone = None

    def is_logged_in(self) -> bool:
        return self._active_client is not None

    def get_client(self) -> TelegramClient:
        if self._active_client is None:
            raise RuntimeError("Not logged in to Telegram.")
        return self._active_client

    async def get_status(self) -> dict:
        if not self.is_logged_in():
            return {"logged_in": False}
        me = await self._active_client.get_me()
        return {
            "logged_in": True,
            "phone": self._active_phone,
            "first_name": me.first_name,
            "username": me.username,
        }

    async def list_dialogs(self) -> list[dict]:
        client = self.get_client()
        result = []
        async for d in client.iter_dialogs():
            result.append({
                "id": str(d.id),
                "entity_id": d.id,
                "name": d.name or "(unnamed)",
                # "type": "channel" if d.is_channel else ("group" if d.is_group else "user"),
                "type": d.type,
                "unread_count": d.unread_count,
            })
        return result


    
    # async def list_dialogs(self) -> list[dict]:
    #     client = self.get_client()
    #     result = []
    #     async for d in client.iter_dialogs():
    #         # Determine the dialog type
    #         if d.is_channel:
    #             dialog_type = "channel"
    #         elif d.is_group:
    #             dialog_type = "group"
    #         elif d.is_user:
    #             # Check if it's a bot
    #             try:
    #                 entity = await client.get_entity(d.id)
    #                 if hasattr(entity, 'bot') and entity.bot:
    #                     dialog_type = "bot"
    #                 else:
    #                     dialog_type = "user"
    #             except Exception:
    #                 dialog_type = "user"
    #         else:
    #             dialog_type = "other"
            
    #         result.append({
    #             "id": str(d.id),
    #             "entity_id": d.id,
    #             "name": d.name or "(unnamed)",
    #             "type": dialog_type,
    #             "unread_count": d.unread_count,
    #         })
    #     return result



manager = TelegramManager()

from pydantic import BaseModel
from fastapi import APIRouter, HTTPException

from app.telegram_client import manager as tg_manager

router = APIRouter(prefix="/api/dialogs", tags=["dialogs"])


class SendMessageRequest(BaseModel):
    text: str


@router.get("")
async def list_dialogs():
    if not tg_manager.is_logged_in():
        raise HTTPException(401, "Not logged in")
    return await tg_manager.list_dialogs()


@router.get("/{dialog_id}/messages")
async def get_messages(dialog_id: int, limit: int = 40, offset_id: int = 0):
    if not tg_manager.is_logged_in():
        raise HTTPException(401, "Not logged in")
    try:
        return await tg_manager.get_messages(dialog_id, limit=limit, offset_id=offset_id)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(400, str(e))


@router.post("/{dialog_id}/messages")
async def send_message(dialog_id: int, req: SendMessageRequest):
    if not tg_manager.is_logged_in():
        raise HTTPException(401, "Not logged in")
    if not req.text.strip():
        raise HTTPException(400, "Message text cannot be empty")
    try:
        return await tg_manager.send_message(dialog_id, req.text)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(400, str(e))

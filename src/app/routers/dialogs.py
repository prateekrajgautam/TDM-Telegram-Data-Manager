from pydantic import BaseModel
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

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


@router.get("/{dialog_id}/messages/{message_id}/media")
async def get_message_media(dialog_id: int, message_id: int):
    """Streams the media of a single message through this server so it can
    be rendered inline in the chat sidebar (img/video/audio tags need a
    same-origin URL — Telegram has no public direct media links)."""
    if not tg_manager.is_logged_in():
        raise HTTPException(401, "Not logged in")
    try:
        msg = await tg_manager.get_single_message(dialog_id, message_id)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(400, str(e))
    if not msg or not msg.media:
        raise HTTPException(404, "No media on this message")

    mime = msg.file.mime_type if msg.file and msg.file.mime_type else "application/octet-stream"

    async def streamer():
        async for chunk in tg_manager.iter_media_chunks(msg):
            yield chunk

    headers = {}
    if msg.file and msg.file.name:
        headers["Content-Disposition"] = f'inline; filename="{msg.file.name}"'
    return StreamingResponse(streamer(), media_type=mime, headers=headers)

from fastapi import APIRouter, HTTPException

from app.telegram_client import manager as tg_manager

router = APIRouter(prefix="/api/dialogs", tags=["dialogs"])


@router.get("")
async def list_dialogs():
    if not tg_manager.is_logged_in():
        raise HTTPException(401, "Not logged in")
    return await tg_manager.list_dialogs()

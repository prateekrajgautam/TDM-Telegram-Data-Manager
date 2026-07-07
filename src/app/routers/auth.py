from fastapi import APIRouter, HTTPException

from app.schemas import SendCodeRequest, SubmitCodeRequest, SubmitPasswordRequest, AuthStatus
from app.telegram_client import manager as tg_manager

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.get("/status", response_model=AuthStatus)
async def status():
    return await tg_manager.get_status()


@router.post("/send-code")
async def send_code(req: SendCodeRequest):
    try:
        await tg_manager.send_code(req.phone)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(400, str(e))
    return {"status": "code_sent"}


@router.post("/submit-code")
async def submit_code(req: SubmitCodeRequest):
    try:
        result = await tg_manager.submit_code(req.phone, req.code)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(400, str(e))
    return {"status": result}


@router.post("/submit-password")
async def submit_password(req: SubmitPasswordRequest):
    try:
        await tg_manager.submit_password(req.phone, req.password)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(400, str(e))
    return {"status": "ok"}


@router.post("/logout")
async def logout():
    await tg_manager.logout()
    return {"status": "logged_out"}

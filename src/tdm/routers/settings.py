import json

from fastapi import APIRouter, HTTPException

from app.database import get_session, StorageTarget
from app.schemas import StorageTargetIn, StorageTargetOut
from app.storage import build_backend

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("/storage-targets", response_model=list[StorageTargetOut])
async def list_storage_targets():
    with get_session() as db:
        targets = db.query(StorageTarget).all()
        return [StorageTargetOut(id=t.id, name=t.name, type=t.type, is_default=t.is_default) for t in targets]


@router.post("/storage-targets", response_model=StorageTargetOut)
async def create_storage_target(req: StorageTargetIn):
    with get_session() as db:
        if req.is_default:
            db.query(StorageTarget).update({StorageTarget.is_default: False})
        target = StorageTarget(
            name=req.name,
            type=req.type,
            config_json=json.dumps(req.config),
            is_default=req.is_default,
        )
        db.add(target)
        db.flush()
        return StorageTargetOut(id=target.id, name=target.name, type=target.type, is_default=target.is_default)


@router.post("/storage-targets/test")
async def test_storage_target(req: StorageTargetIn):
    try:
        backend = build_backend(req.type, req.config)
        backend.close()
    except Exception as e:  # noqa: BLE001
        raise HTTPException(400, f"Connection failed: {e}")
    return {"status": "ok"}


@router.delete("/storage-targets/{target_id}")
async def delete_storage_target(target_id: int):
    with get_session() as db:
        target = db.query(StorageTarget).get(target_id)
        if not target:
            raise HTTPException(404, "Not found")
        db.delete(target)
    return {"status": "deleted"}

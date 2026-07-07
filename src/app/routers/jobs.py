import json

from fastapi import APIRouter, HTTPException

from app.database import get_session, Job
from app.jobs import enqueue
from app.schemas import CreateDownloadJob, CreateExportJob, CreateForwardJob, JobOut

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.post("/download", response_model=JobOut)
async def create_download_job(req: CreateDownloadJob):
    with get_session() as db:
        job = Job(
            job_type="download",
            dialog_id=req.dialog_id,
            dialog_name=req.dialog_name,
            storage_target_id=req.storage_target_id,
            options_json=json.dumps({
                "media_types": req.media_types,
                "limit": req.limit,
                "min_id": req.min_id,
                "max_id": req.max_id,
                "subfolder": req.subfolder,
            }),
        )
        db.add(job)
        db.flush()
        job_id = job.id
        out = JobOut.model_validate(job)
    enqueue(job_id)
    return out


@router.post("/export", response_model=JobOut)
async def create_export_job(req: CreateExportJob):
    with get_session() as db:
        job = Job(
            job_type="export",
            dialog_id=req.dialog_id,
            dialog_name=req.dialog_name,
            storage_target_id=req.storage_target_id,
            options_json=json.dumps({"format": req.format, "limit": req.limit}),
        )
        db.add(job)
        db.flush()
        job_id = job.id
        out = JobOut.model_validate(job)
    enqueue(job_id)
    return out


@router.post("/forward", response_model=JobOut)
async def create_forward_job(req: CreateForwardJob):
    if not req.confirm_tos:
        raise HTTPException(
            400,
            "Forwarding must be explicitly confirmed. Bulk/automated forwarding can violate "
            "Telegram's Terms of Service if used for spam — only forward content you have the "
            "right to share, at a reasonable pace.",
        )
    if req.target_dialog_id == req.dialog_id:
        raise HTTPException(400, "Source and target chat cannot be the same.")
    with get_session() as db:
        job = Job(
            job_type="forward",
            dialog_id=req.dialog_id,
            dialog_name=req.dialog_name,
            options_json=json.dumps({
                "target_dialog_id": req.target_dialog_id,
                "target_dialog_name": req.target_dialog_name,
                "media_types": req.media_types,
                "limit": req.limit,
            }),
        )
        db.add(job)
        db.flush()
        job_id = job.id
        out = JobOut.model_validate(job)
    enqueue(job_id)
    return out


@router.get("", response_model=list[JobOut])
async def list_jobs():
    with get_session() as db:
        jobs = db.query(Job).order_by(Job.id.desc()).limit(200).all()
        return [JobOut.model_validate(j) for j in jobs]


@router.get("/{job_id}", response_model=JobOut)
async def get_job(job_id: int):
    with get_session() as db:
        job = db.query(Job).get(job_id)
        if not job:
            raise HTTPException(404, "Job not found")
        return JobOut.model_validate(job)


@router.post("/{job_id}/cancel")
async def cancel_job(job_id: int):
    with get_session() as db:
        job = db.query(Job).get(job_id)
        if not job:
            raise HTTPException(404, "Job not found")
        if job.status in ("pending", "running"):
            job.status = "cancelled"
    return {"status": "cancelled"}

import json

from fastapi import APIRouter, HTTPException

from app.database import get_session, Job, MediaItem
from app.jobs import enqueue
from app.schemas import CreateExportJob, CreateTransferJob, JobOut

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


def _to_job_out(job: Job) -> JobOut:
    with get_session() as db:
        failed_count = db.query(MediaItem).filter_by(job_id=job.id, status="failed").count()
    out = JobOut.model_validate(job)
    out.failed_count = failed_count
    return out


@router.post("/transfer", response_model=list[JobOut])
async def create_transfer_job(req: CreateTransferJob):
    """Creates a download job, a forward job, or both - sharing the same
    dialog/media-type/date-range filters - depending on `action`."""
    if req.action not in ("download", "forward", "both"):
        raise HTTPException(400, "action must be 'download', 'forward', or 'both'")

    do_download = req.action in ("download", "both")
    do_forward = req.action in ("forward", "both")

    if do_forward:
        if not req.confirm_tos:
            raise HTTPException(
                400,
                "Forwarding must be explicitly confirmed. Bulk/automated forwarding can violate "
                "Telegram's Terms of Service if used for spam - only forward content you have the "
                "right to share, at a reasonable pace.",
            )
        if not req.target_dialog_id:
            raise HTTPException(400, "target_dialog_id is required to forward.")
        if req.target_dialog_id == req.dialog_id:
            raise HTTPException(400, "Source and target chat cannot be the same.")

    created: list[Job] = []

    with get_session() as db:
        if do_download:
            job = Job(
                job_type="download",
                dialog_id=req.dialog_id,
                dialog_name=req.dialog_name,
                storage_target_id=req.storage_target_id,
                options_json=json.dumps({
                    "media_types": req.media_types,
                    "limit": req.limit,
                    "date_from": req.date_from,
                    "date_to": req.date_to,
                }),
            )
            db.add(job)
            db.flush()
            created.append(job)

        if do_forward:
            job = Job(
                job_type="forward",
                dialog_id=req.dialog_id,
                dialog_name=req.dialog_name,
                options_json=json.dumps({
                    "target_dialog_id": req.target_dialog_id,
                    "target_dialog_name": req.target_dialog_name,
                    "media_types": req.media_types,
                    "limit": req.limit,
                    "date_from": req.date_from,
                    "date_to": req.date_to,
                    "remove_forward_tag": req.remove_forward_tag,
                }),
            )
            db.add(job)
            db.flush()
            created.append(job)

        outs = [JobOut.model_validate(j) for j in created]
        job_ids = [j.id for j in created]

    for job_id in job_ids:
        enqueue(job_id)
    return outs


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


@router.get("", response_model=list[JobOut])
async def list_jobs():
    with get_session() as db:
        jobs = db.query(Job).order_by(Job.id.desc()).limit(200).all()
    return [_to_job_out(j) for j in jobs]


@router.get("/{job_id}", response_model=JobOut)
async def get_job(job_id: int):
    with get_session() as db:
        job = db.query(Job).get(job_id)
        if not job:
            raise HTTPException(404, "Job not found")
    return _to_job_out(job)


@router.post("/{job_id}/cancel")
async def cancel_job(job_id: int):
    with get_session() as db:
        job = db.query(Job).get(job_id)
        if not job:
            raise HTTPException(404, "Job not found")
        if job.status in ("pending", "running"):
            job.status = "cancelled"
    return {"status": "cancelled"}


@router.post("/{job_id}/pause", response_model=JobOut)
async def pause_job(job_id: int):
    """Marks a running/pending job as paused. The worker checks status
    between each message, so a running job stops within a moment; a
    still-queued one simply won't start. Already-completed items stay
    recorded — Resume picks back up from there."""
    with get_session() as db:
        job = db.query(Job).get(job_id)
        if not job:
            raise HTTPException(404, "Job not found")
        if job.job_type not in ("download", "forward"):
            raise HTTPException(400, "Only download/forward jobs support pause.")
        if job.status not in ("pending", "running"):
            raise HTTPException(400, "Only pending or running jobs can be paused.")
        job.status = "paused"
        out = JobOut.model_validate(job)
    return out


@router.post("/{job_id}/resume", response_model=JobOut)
async def resume_job(job_id: int):
    """Re-enqueues a paused job. It resumes from where it left off — items
    already recorded as done/forwarded in a prior run are skipped."""
    with get_session() as db:
        job = db.query(Job).get(job_id)
        if not job:
            raise HTTPException(404, "Job not found")
        if job.status != "paused":
            raise HTTPException(400, "Only paused jobs can be resumed.")
        job.status = "pending"
        job.error = None
        job_id = job.id
        out = JobOut.model_validate(job)
    enqueue(job_id)
    return out


@router.post("/{job_id}/retry", response_model=JobOut)
async def retry_job(job_id: int):
    with get_session() as db:
        job = db.query(Job).get(job_id)
        if not job:
            raise HTTPException(404, "Job not found")
        if job.job_type not in ("download", "forward"):
            raise HTTPException(400, "Only download/forward jobs support retry.")
        if job.status not in ("failed", "completed_with_errors", "cancelled"):
            raise HTTPException(400, "Only failed, partially-completed, or cancelled jobs can be retried.")
        job.status = "pending"
        job.error = None
        job_id = job.id
        out = JobOut.model_validate(job)
    enqueue(job_id)
    return out

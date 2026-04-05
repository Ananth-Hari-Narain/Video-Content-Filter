from __future__ import annotations

import mimetypes
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from cli import cli

from backend.api.schemas import JobCreateResponse, JobMode, JobStatus, JobStatusResponse, MediaType
from backend.config import AUDIO_EXTENSIONS, JOBS_DIR, VIDEO_EXTENSIONS
from backend.services.job_store import JobRecord, job_store
from backend.services.processor import process_job

router = APIRouter(prefix="/api/v1", tags=["jobs"])


def _detect_media_type(filename: str, content_type: str | None) -> MediaType:
    ext = Path(filename).suffix.lower()
    if ext in AUDIO_EXTENSIONS:
        return MediaType.audio
    if ext in VIDEO_EXTENSIONS:
        return MediaType.video

    guessed, _ = mimetypes.guess_type(filename)
    inferred = content_type or guessed or ""
    if inferred.startswith("audio/"):
        return MediaType.audio
    if inferred.startswith("video/"):
        return MediaType.video

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Unsupported file type. Please upload an audio or video file.",
    )


def _normalize_mode(media_type: MediaType, mode: str) -> JobMode:
    if media_type == MediaType.audio:
        if mode != JobMode.bleep.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Audio files only support mode 'bleep'.",
            )
        return JobMode.bleep

    # video
    if mode not in {JobMode.audio_only.value, JobMode.full.value}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Video files support mode 'audio-only' or 'full'.",
        )
    return JobMode(mode)


@router.post("/jobs", response_model=JobCreateResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_job(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    mode: str = Form(...),
) -> JobCreateResponse:
    if job_store.has_active_job():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A file is already being processed. Please wait for it to finish.",
        )

    if not file.filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing filename.")

    media_type = _detect_media_type(file.filename, file.content_type)
    normalized_mode = _normalize_mode(media_type, mode)

    job_id = str(uuid4())
    work_dir = JOBS_DIR / job_id
    work_dir.mkdir(parents=True, exist_ok=True)

    input_path = work_dir / file.filename
    with input_path.open("wb") as destination:
        while chunk := await file.read(1024 * 1024):
            destination.write(chunk)

    if media_type == MediaType.audio:
        output_path = Path(cli._default_audio_output_path(str(input_path)))
    else:
        output_path = Path(cli._default_video_output_path(str(input_path), normalized_mode.value))

    record = JobRecord(
        job_id=job_id,
        filename=file.filename,
        media_type=media_type,
        mode=normalized_mode,
        input_path=input_path,
        output_path=output_path,
        work_dir=work_dir,
    )
    job_store.create_job(record)
    background_tasks.add_task(process_job, job_id)

    return JobCreateResponse(
        job_id=job_id,
        status=JobStatus.queued,
        media_type=media_type,
        mode=normalized_mode,
        message="File received. Filtering profanity.",
    )


@router.get("/jobs/{job_id}", response_model=JobStatusResponse)
def get_job(job_id: str) -> JobStatusResponse:
    record = job_store.get(job_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found.")

    download_url = None
    message = "Filtering profanity"

    if record.status == JobStatus.completed:
        message = "Filtering complete"
        download_url = f"/api/v1/jobs/{job_id}/download"
    elif record.status == JobStatus.failed:
        message = "Filtering failed"

    return JobStatusResponse(
        job_id=record.job_id,
        status=record.status,
        media_type=record.media_type,
        mode=record.mode,
        filename=record.filename,
        download_url=download_url,
        message=message,
        error=record.error,
    )


@router.get("/jobs/{job_id}/download")
def download_job(job_id: str) -> FileResponse:
    record = job_store.get(job_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found.")

    if record.status != JobStatus.completed:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="File is not ready for download yet.",
        )

    if not record.output_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Output file missing.")

    return FileResponse(path=record.output_path, filename=record.output_path.name)

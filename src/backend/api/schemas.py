from pydantic import BaseModel
from uuid import UUID

class JobRequest(BaseModel):
    filterSubtitles: bool
    fileSize: int  # In bytes
    fileType: str

class JobCreateResponse(BaseModel):
    job_id: UUID  # Important if user closes their tab
    upload_url: dict  # Presigned URL to upload to R2 bucket

class QueuedJob(BaseModel):
    job_id: UUID
    download_url: str
    filterSubtitles: bool

from pydantic import BaseModel, Field
from uuid import UUID

MAX_FILE_SIZE_BYTES = 10 * 1024**3  # 10 GiB

class JobRequest(BaseModel):
    filterSubtitles: bool
    fileSize: int = Field(ge=1, le=MAX_FILE_SIZE_BYTES)  # In bytes
    fileType: str

class JobCreateResponse(BaseModel):
    job_id: UUID  # Important if user closes their tab
    upload_url: dict  # Presigned URL to upload to R2 bucket

class QueuedJob(BaseModel):
    job_id: UUID
    download_url: str
    filterSubtitles: bool

class JobStatusResponse(BaseModel):
    status: str
    stage: str
    percent: int
    download_link: str = ""  # Empty string indicates nothing to download

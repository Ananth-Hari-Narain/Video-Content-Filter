from enum import Enum
from pydantic import BaseModel


class JobStatus(str, Enum):
    queued = "queued"
    processing = "processing"
    completed = "completed"
    failed = "failed"


class MediaType(str, Enum):
    audio = "audio"
    video = "video"


class JobMode(str, Enum):
    bleep = "bleep"
    audio_only = "audio-only"
    full = "full"


class JobCreateResponse(BaseModel):
    job_id: str
    status: JobStatus
    media_type: MediaType
    mode: JobMode
    message: str


class JobStatusResponse(BaseModel):
    job_id: str
    status: JobStatus
    media_type: MediaType
    mode: JobMode
    message: str
    filename: str
    download_url: str | None = None
    error: str | None = None

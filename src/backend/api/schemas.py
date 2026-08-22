from enum import Enum
from pydantic import BaseModel
import mimetypes

class JobRequest(BaseModel):
    fileName: str
    filterSubtitles: bool = True
    fileSize: int  # In bytes
    fileType: str

class JobCreateResponse(BaseModel):
    job_id: str  # Important if user closes their tab
    upload_url: str  # Presigned URL to upload to R2 bucket

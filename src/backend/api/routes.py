"""TODO
- GET, SET, DELETE with job storage
- Upload to rabbitMQ
"""

from __future__ import annotations

# For loading r2.env
from dotenv import load_dotenv
import os
from pathlib import Path

# Web libraries
from fastapi import APIRouter, HTTPException
import boto3
from botocore.exceptions import ClientError
from uuid import uuid4, UUID
import redis

# Other
from typing import Optional
from dataclasses import dataclass
import re

# My modules
from backend.api.schemas import *
from backend.config import AUDIO_EXTENSIONS, VIDEO_EXTENSIONS

# Initialisation
BASE_DIR = Path(__file__).resolve().parents[0]
if not load_dotenv(BASE_DIR / "file.env"):
	print(str(BASE_DIR))

router = APIRouter(prefix="/api/v1", tags=["jobs"])

bucket_name = "vcf-bucket"

r2 = boto3.client(
	"s3",
	endpoint_url=f"https://{os.getenv("CLOUDFLARE_ACCOUNT_ID")}.r2.cloudflarestorage.com",
	aws_access_key_id=os.getenv("R2_ACCESS_KEY_ID"),
	aws_secret_access_key=os.getenv("R2_SECRET_ACCESS_KEY"),
	region_name="auto",
)

redis_temp_job_store_url = os.getenv("UPSTASH_REDIS_JOB_STORE_URL")
if redis_temp_job_store_url is None:
	raise Exception("UPSTASH_REDIS_JOB_STORE_URL not loaded from dotenv file")
	
redis_temp_job_store = redis.Redis.from_url(redis_temp_job_store_url)

def is_valid_filetype(type: str) -> tuple[int, str, str]:
	"""
	Ensures filetype is a mimetype and is a valid type for this program. This includes only video and/or audio files. 
	
	:return: HTTP status code (200 if filetype is valid). Also returns description of why mimetype failed and a version
	with no arguments.
	"""
	# RFC 6838-based mimetype format: type/subtype (parameters stripped before matching)
	MIME_TYPE_RE = re.compile(
		r'^[a-zA-Z0-9][a-zA-Z0-9!#$&\-\^_.+]*'
		r'/'
		r'[a-zA-Z0-9][a-zA-Z0-9!#$&\-\^_.+]*$'
	)

	EXCEPTIONS = {
		"application/ogg",             # Ogg container (audio or video)
		"application/mp4",             # MP4 container, rarely seen with this prefix
		"application/x-mpegurl",       # HLS playlist
		"application/vnd.apple.mpegurl",  # HLS playlist (Apple's registered form)
		"application/dash+xml",        # MPEG-DASH manifest
		"application/x-matroska",      # Matroska container (.mkv), sometimes seen this way
		"application/x-flv",           # Flash video
	}

	# remove parameters
	base = type.split(';', 1)[0].strip().lower()
	
	if not MIME_TYPE_RE.match(base):
		return (401, "File is not a valid mimetype.", base)

	if base not in EXCEPTIONS and base.split('/')[0] not in ("audio", "video"):
		return (415, "File not supported by this application.", base)

	return (200, "", base)

@router.post("/job/")
def create_job_request(job: JobRequest):
	"""
	Generate pre-signed URL and upload job information temporarily to storage. Not asynchronous as boto3 is synchronous 
	so no point for now.
	"""
	# Validate file type that client has provided
	http_code, error_msg, base_type = is_valid_filetype(job.fileType)
	if http_code != 200:
		raise HTTPException(
			status_code=http_code,
			detail=error_msg,
		)

	try:
		job_id = uuid4()
		upload_url = r2.generate_presigned_post(
			Bucket=bucket_name,
			Key=str(job_id),
			Fields={"Content-Type": base_type},
			Conditions=[
				{"Content-Type": base_type},
				["content-length-range", 1, job.fileSize]  # Allow any file smaller than the given size
			],
			ExpiresIn=3600  # 1 hour to upload
		)
		
		download_url = r2.generate_presigned_url(
			"get_object",
			Params={
				"Bucket": bucket_name,
				"Key": str(job_id),
			},  
		)
				
		# Upload to redis temporary job storage
		redis_temp_job_store.hset(
			name=str(job_id),
			mapping={
				"presigned_url": str(download_url),
				"filterSubtitles": int(job.filterSubtitles),
			}
		)

		return { 
			"status": 201,
			"job_id": job_id,
			"upload_url": upload_url,
		}
	
	except ClientError as _:
		raise HTTPException(
			status_code=500, 
			detail="Could not access object storage."
		)


@router.post("job/{job_id}/upload_status")
async def confirm_upload_status(job_id: UUID):
	"""
	This route is used to allow the client to tell the server that the upload is complete, and can be put into a queue.
	"""
    # Get the download URL and job information from redis
	# Upload job to RabbitMQ
	# Add job to Redis cache so workers can update it regularly.

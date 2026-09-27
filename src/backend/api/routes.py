from __future__ import annotations

import re
from uuid import uuid4, UUID

from fastapi import APIRouter, Depends, HTTPException
from botocore.exceptions import ClientError

from backend.api.schemas import JobRequest, JobCreateResponse, JobStatusResponse, QueuedJob
from backend.api.settings import Settings
from backend.api.dependencies import (
	get_settings,
	get_r2_client,
	get_redis_client,
	get_rabbitmq_channel,
	get_db_connection,
)
from backend.api.services.storage import R2Storage
from backend.api.services.job_cache import JobCache
from backend.api.services.job_queue import JobQueue
from backend.api.services.job_repository import JobRepository

router = APIRouter(prefix="/api/v1", tags=["jobs"])


def get_storage(
	settings: Settings = Depends(get_settings),
	client=Depends(get_r2_client),
) -> R2Storage:
	return R2Storage(client=client, bucket_name=settings.bucket_name)


def get_job_cache(client=Depends(get_redis_client)) -> JobCache:
	return JobCache(client=client)


def get_job_queue(
	settings: Settings = Depends(get_settings),
	channel=Depends(get_rabbitmq_channel),
) -> JobQueue:
	return JobQueue(channel=channel, queue_name=settings.job_queue_name)


def get_job_repository(connection=Depends(get_db_connection)) -> JobRepository:
	return JobRepository(connection=connection)


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
def create_job_request(
	job: JobRequest,
	storage: R2Storage = Depends(get_storage),
	job_cache: JobCache = Depends(get_job_cache),
):
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
		upload_url = storage.create_presigned_upload(job_id, base_type, job.fileSize)
		download_url = storage.create_presigned_download(job_id)

		job_cache.save_pending_job(
			job_id=job_id,
			presigned_url=str(download_url),
			filter_subtitles=job.filterSubtitles,
			ttl=3600,
		)

		return JobCreateResponse(
			job_id=job_id,
			upload_url=upload_url,
		)

	except ClientError as _:
		raise HTTPException(
			status_code=500, 
			detail="Could not access object storage."
		)


@router.post("/job/{job_id}/upload_status")
async def confirm_upload_status(
	job_id: UUID,
	storage: R2Storage = Depends(get_storage),
	job_cache: JobCache = Depends(get_job_cache),
	job_queue: JobQueue = Depends(get_job_queue),
	job_repository: JobRepository = Depends(get_job_repository),
):
	"""
	This route is used to allow the client to tell the server that the upload is complete, and can be put into a queue.
	"""
	pending_job = job_cache.get_pending_job(job_id)
	if pending_job is None:
		raise HTTPException(
			status_code=404,
			detail=f"No job found for job_id={job_id}",
		)

	# Check file is actually uploaded
	try:
		object_info = storage.get_uploaded_object_info(job_id)
	except ClientError as e:
		if e.response["Error"]["Code"] in ("404", "NoSuchKey"):
			raise HTTPException(
				status_code=404,
				detail=f"File for job {job_id} not found. Wait for the file to upload before trying again."
			)
		raise

	# Upload job to RabbitMQ
	job_queue.publish(
		QueuedJob(
			job_id=job_id,
			download_url=pending_job.presigned_url,
			filterSubtitles=pending_job.filter_subtitles,
		)
	)

	# Add job to Postgres database. DB does two things: tracks progress and provides a log of all processed jobs
	job_repository.create_job(
		job_id=job_id,
		filter_subtitles=pending_job.filter_subtitles,
		file_type=object_info.file_type,
		file_size=object_info.file_size,
	)


@router.get("/job/{job_id}")
def get_job_status(
	job_id: UUID,
	job_repository: JobRepository = Depends(get_job_repository),
) -> JobStatusResponse:
	"""
	Returns the current status, stage, and percent progress of a job from the Postgres database.
	"""
	record = job_repository.get_status(job_id)

	if record is None:
		raise HTTPException(
			status_code=404,
			detail=f"No job found for job_id={job_id}",
		)

	return JobStatusResponse(status=record.status, stage=record.stage, percent=record.percent)

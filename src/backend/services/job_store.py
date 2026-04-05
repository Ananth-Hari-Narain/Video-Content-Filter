from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Dict

from backend.api.schemas import JobMode, JobStatus, MediaType


@dataclass
class JobRecord:
    job_id: str
    filename: str
    media_type: MediaType
    mode: JobMode
    input_path: Path
    output_path: Path
    work_dir: Path
    status: JobStatus = JobStatus.queued
    error: str | None = None


class JobStore:
    def __init__(self) -> None:
        self._jobs: Dict[str, JobRecord] = {}
        self._active_job_id: str | None = None
        self._lock = Lock()

    def create_job(self, record: JobRecord) -> None:
        with self._lock:
            self._jobs[record.job_id] = record
            self._active_job_id = record.job_id

    def has_active_job(self) -> bool:
        with self._lock:
            if self._active_job_id is None:
                return False
            current = self._jobs.get(self._active_job_id)
            return current is not None and current.status in {JobStatus.queued, JobStatus.processing}

    def get(self, job_id: str) -> JobRecord | None:
        with self._lock:
            return self._jobs.get(job_id)

    def set_status(self, job_id: str, status: JobStatus, error: str | None = None) -> None:
        with self._lock:
            job = self._jobs[job_id]
            job.status = status
            job.error = error
            if status in {JobStatus.completed, JobStatus.failed} and self._active_job_id == job_id:
                self._active_job_id = None


job_store = JobStore()

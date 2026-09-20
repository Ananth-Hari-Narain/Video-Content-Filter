from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
from uuid import UUID


@dataclass
class JobStatusRecord:
    status: str
    stage: str
    percent: int


class JobRepository:
    """Wraps Postgres reads/writes for job tracking. Table: `jobs`."""

    def __init__(self, connection):
        self._connection = connection

    def create_job(
        self,
        job_id: UUID,
        filter_subtitles: bool,
        file_type: str,
        file_size: int,
    ) -> None:
        with self._connection.cursor() as cur:
            cur.execute(
                "INSERT INTO jobs (id, filter_subtitles, file_type, file_size, stage, status, created_at) "
                "VALUES (%s, %s, %s, %s, %s, %s, NOW())",
                (str(job_id), filter_subtitles, file_type, file_size, "", "Queued"),
            )
        self._connection.commit()

    def get_status(self, job_id: UUID) -> Optional[JobStatusRecord]:
        with self._connection.cursor() as cur:
            cur.execute(
                "SELECT status, stage, percent FROM jobs WHERE id = %s",
                (str(job_id),),
            )
            row = cur.fetchone()

        if row is None:
            return None

        status, stage, percent = row
        return JobStatusRecord(status=status, stage=stage, percent=percent)

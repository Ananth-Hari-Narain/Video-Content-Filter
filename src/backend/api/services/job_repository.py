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
    """Wraps Postgres reads/writes for job tracking. Table: `job`."""

    def __init__(self, connection):
        self._connection = connection

    def create_job(
        self,
        job_id: UUID,
        filter_subtitles: bool,
        file_type: str,
        file_size: int,
    ) -> bool:
        """Insert the job row. Returns False if a row for this job_id already exists."""
        with self._connection.cursor() as cur:
            cur.execute(
                "INSERT INTO job (id, filter_subtitles, file_type, file_size, stage, status, created_at) "
                "VALUES (%s, %s, %s, %s, %s, %s, NOW()) "
                "ON CONFLICT (id) DO NOTHING",
                (str(job_id), filter_subtitles, file_type, file_size, "", "queued"),
            )
            inserted = cur.rowcount == 1
        self._connection.commit()
        return inserted

    def delete_job(self, job_id: UUID) -> None:
        with self._connection.cursor() as cur:
            cur.execute("DELETE FROM job WHERE id = %s", (str(job_id),))
        self._connection.commit()

    def update_progress(self, job_id: UUID, stage: str, percent: int, status: str = "running") -> None:
        with self._connection.cursor() as cur:
            cur.execute(
                "UPDATE job SET status = %s, stage = %s, percent = %s WHERE id = %s",
                (status, stage, percent, str(job_id)),
            )
        self._connection.commit()

    def get_status(self, job_id: UUID) -> Optional[JobStatusRecord]:
        with self._connection.cursor() as cur:
            cur.execute(
                "SELECT status, stage, percent FROM job WHERE id = %s",
                (str(job_id),),
            )
            row = cur.fetchone()

        if row is None:
            return None

        status, stage, percent = row
        return JobStatusRecord(status=status, stage=stage, percent=percent)

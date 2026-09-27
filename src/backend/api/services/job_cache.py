from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
from uuid import UUID
import redis


@dataclass
class PendingJob:
    presigned_url: str
    filter_subtitles: bool


class JobCache:
    """Wraps the Redis-backed temporary store for jobs awaiting upload confirmation."""

    def __init__(self, client: redis.Redis):
        self._client = client

    def save_pending_job(self, job_id: UUID, presigned_url: str, filter_subtitles: bool, ttl: int) -> None:
        self._client.hset(
            name=str(job_id),
            mapping={
                "presigned_url": presigned_url,
                "filterSubtitles": int(filter_subtitles),
            },
        )

        self._client.expire(name=str(job_id), time=ttl)

    def get_pending_job(self, job_id: UUID) -> Optional[PendingJob]:
        presigned_url, filter_subtitles_raw = self._client.hmget(
            str(job_id), ["presigned_url", "filterSubtitles"]
        )

        if presigned_url is None or filter_subtitles_raw is None:
            return None

        return PendingJob(
            presigned_url=presigned_url.decode() if isinstance(presigned_url, bytes) else presigned_url,
            filter_subtitles=bool(int(filter_subtitles_raw)),
        )

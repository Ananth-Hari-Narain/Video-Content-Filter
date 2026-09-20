from __future__ import annotations

from backend.api.schemas import QueuedJob


class JobQueue:
    """Wraps publishing queued jobs to RabbitMQ."""

    def __init__(self, channel, queue_name: str):
        self._channel = channel
        self._queue_name = queue_name

    def publish(self, job: QueuedJob) -> None:
        self._channel.basic_publish(
            exchange="",
            routing_key=self._queue_name,
            body=job.model_dump_json(),
        )

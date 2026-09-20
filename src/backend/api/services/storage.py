from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID


@dataclass
class UploadedObjectInfo:
    file_size: int
    file_type: str


class R2Storage:
    """Thin wrapper around the R2 (S3-compatible) client used for job uploads."""

    def __init__(self, client, bucket_name: str):
        self._client = client
        self._bucket_name = bucket_name

    def create_presigned_upload(self, job_id: UUID, content_type: str, max_file_size: int) -> dict:
        return self._client.generate_presigned_post(
            Bucket=self._bucket_name,
            Key=str(job_id),
            Fields={"Content-Type": content_type},
            Conditions=[
                {"Content-Type": content_type},
                ["content-length-range", 1, max_file_size],
            ],
            ExpiresIn=3600,  # 1 hour to upload
        )

    def create_presigned_download(self, job_id: UUID) -> str:
        return self._client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self._bucket_name, "Key": str(job_id)},
        )

    def get_uploaded_object_info(self, job_id: UUID) -> UploadedObjectInfo:
        head = self._client.head_object(Bucket=self._bucket_name, Key=str(job_id))
        return UploadedObjectInfo(file_size=head["ContentLength"], file_type=head["ContentType"])

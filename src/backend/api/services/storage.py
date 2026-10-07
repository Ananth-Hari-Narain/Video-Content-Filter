from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
from uuid import UUID


@dataclass
class ObjectInfo:
    file_size: int
    file_type: str


class R2Storage:
    """Thin wrapper around the R2 (S3-compatible) client used for job uploads."""

    def __init__(self, client, bucket_name: str):
        self._client = client
        self._bucket_name = bucket_name

    def create_presigned_upload(
        self,
        job_id: UUID,
        file_info: Optional[ObjectInfo] = None,
        expires_in: int = 3600,
    ) -> str:
        """
        Presigned PUT URL. R2 does not support presigned POST, so there are no POST policy conditions (size range):
        only the Content-Type is signed. Hence, file_info.file_size is unused.
        """
        params = {"Bucket": self._bucket_name, "Key": str(job_id)}
        if file_info:
            params["ContentType"] = file_info.file_type
        return self._client.generate_presigned_url("put_object", Params=params, ExpiresIn=expires_in)

    def create_presigned_download(self, job_id: UUID, expires_in: int = 3600, key: Optional[str] = None) -> str:
        return self._client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self._bucket_name, "Key": key or str(job_id)},
            ExpiresIn=expires_in,
        )

    def upload_output(self, job_id: UUID, path) -> str:
        """Upload a processed file and return its presigned download URL."""
        key = self.output_key(job_id)
        # upload_file streams from disk and switches to multipart for large files
        self._client.upload_file(
            str(path),
            self._bucket_name,
            key,
        )
        return self.create_presigned_download(job_id, 600, key=key)  # 10 minutes

    @staticmethod
    def output_key(job_id: UUID | str) -> str:
        # Separate from the input object, which is keyed by the bare job id
        return f"output/{job_id}"

    def get_uploaded_object_info(self, job_id: UUID) -> ObjectInfo:
        head = self._client.head_object(Bucket=self._bucket_name, Key=str(job_id))
        return ObjectInfo(file_size=head["ContentLength"], file_type=head["ContentType"])

"""Uploads straight to the bucket using the presigned PUT URL from R2Storage (not via any API route)."""

import time
from uuid import uuid4

import httpx
import pytest
from botocore.exceptions import ClientError

from backend.api.services.storage import ObjectInfo

pytestmark = pytest.mark.integration

CONTENT_TYPE = "video/mp4"
MAX_SIZE = 1024


def _upload(presigned: str, body: bytes, content_type: str = CONTENT_TYPE) -> httpx.Response:
    """PUT `body` to the presigned URL. `content_type` overrides the signed Content-Type header."""
    return httpx.put(presigned, content=body, headers={"Content-Type": content_type})


def _object_exists(s3_client, bucket: str, job_id) -> bool:
    try:
        s3_client.head_object(Bucket=bucket, Key=str(job_id))
        return True
    except ClientError as e:
        if e.response["Error"]["Code"] in ("404", "NoSuchKey", "NotFound"):
            return False
        raise


@pytest.fixture
def job_id():
    return uuid4()


@pytest.fixture
def presigned(storage, job_id) -> str:
    return storage.create_presigned_upload(job_id, ObjectInfo(file_type=CONTENT_TYPE, file_size=MAX_SIZE))


class TestUploadSucceeds:
    def test_one_byte_file(self, presigned, s3_client, storage, job_id):
        response = _upload(presigned, b"x")

        # S3Mock returns 200 here; MinIO and real S3/R2 return 204. Both mean success.
        assert response.status_code in (200, 204)
        assert storage.get_uploaded_object_info(job_id).file_size == 1

    def test_file_exactly_max_length(self, presigned, storage, job_id):
        response = _upload(presigned, b"x" * MAX_SIZE)

        assert response.status_code in (200, 204)
        info = storage.get_uploaded_object_info(job_id)
        assert info.file_size == MAX_SIZE
        assert info.file_type == CONTENT_TYPE

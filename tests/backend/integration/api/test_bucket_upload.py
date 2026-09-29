"""Uploads straight to the bucket using the presigned POST from R2Storage (not via any API route)."""

import time
from uuid import uuid4

import httpx
import pytest
from botocore.exceptions import ClientError

pytestmark = pytest.mark.integration

CONTENT_TYPE = "video/mp4"
MAX_SIZE = 1024


def _upload(presigned: dict, body: bytes, content_type: str = CONTENT_TYPE) -> httpx.Response:
    """POST `body` to the presigned form. `content_type` overrides the signed Content-Type form field."""
    fields = {**presigned["fields"], "Content-Type": content_type}
    return httpx.post(presigned["url"], data=fields, files={"file": ("upload", body, content_type)})


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
def presigned(storage, job_id) -> dict:
    return storage.create_presigned_upload(job_id, CONTENT_TYPE, MAX_SIZE)


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


# NOTE: S3Mock (the local stand-in for R2 used here) does not enforce presigned-POST policy
# conditions - the size range, content-type match, and expiry are all accepted regardless.
# Confirmed against S3Mock (adobe/s3mock) on 2026-09-27: every case below got a 200 back
# instead of being rejected. minio/minio does enforce these (confirmed 2026-09-26) but pulling
# it needs a Docker Hub login on this machine; localstack/localstack now requires a paid
# license just to start. Point `s3_client`/`storage` at MinIO or real R2 to re-enable these.
@pytest.mark.skip(reason="S3Mock does not enforce presigned-POST conditions - see module note")
class TestUploadRejected:
    def test_file_one_byte_over_max_length(self, presigned, s3_client, storage, job_id):
        response = _upload(presigned, b"x" * (MAX_SIZE + 1))

        assert 400 <= response.status_code < 500
        assert not _object_exists(s3_client, storage._bucket_name, job_id)

    def test_zero_byte_file(self, presigned, s3_client, storage, job_id):
        response = _upload(presigned, b"")

        assert 400 <= response.status_code < 500
        assert not _object_exists(s3_client, storage._bucket_name, job_id)

    def test_content_type_differs_from_the_one_signed(self, presigned, s3_client, storage, job_id):
        response = _upload(presigned, b"x", content_type="audio/mpeg")

        assert 400 <= response.status_code < 500
        assert not _object_exists(s3_client, storage._bucket_name, job_id)

    def test_upload_after_ttl_expires(self, storage, s3_client, job_id):
        presigned = storage.create_presigned_upload(job_id, CONTENT_TYPE, MAX_SIZE, expires_in=1)
        time.sleep(3)

        response = _upload(presigned, b"x")

        assert 400 <= response.status_code < 500
        assert not _object_exists(s3_client, storage._bucket_name, job_id)

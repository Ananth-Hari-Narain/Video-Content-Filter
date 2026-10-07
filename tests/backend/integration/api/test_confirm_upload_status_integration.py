import json
from uuid import uuid4

import pytest

from backend.api.services.job_cache import JobCache
from backend.api.schemas import QueuedJob
from .fixtures import TEST_SETTINGS

pytestmark = pytest.mark.integration

CONTENT_TYPE = "video/mp4"
FILE_BODY = b"fake video bytes"


@pytest.fixture
def pending_job(redis_client, s3_client):
    """A job that passed creation (pending in Redis) and whose file has been uploaded to the bucket."""
    job_id = uuid4()
    JobCache(redis_client).save_pending_job(
        job_id=job_id,
        presigned_url=f"{'http://localhost:59000'}/{TEST_SETTINGS.bucket_name}/{job_id}?sig=abc",
        filter_subtitles=True,
        ttl=3600,
    )
    s3_client.put_object(
        Bucket=TEST_SETTINGS.bucket_name, Key=str(job_id), Body=FILE_BODY, ContentType=CONTENT_TYPE
    )
    return job_id


def _confirm(client, job_id):
    return client.post(f"/api/v1/job/{job_id}/upload_status")


class TestConfirmUploadHappyPath:
    def test_job_is_persisted_in_db(self, make_client, pending_job, db_conn):
        response = _confirm(make_client(), pending_job)

        assert response.status_code == 200

        # TODO: once the real schema is in the repo, assert every column (SELECT *) incl. defaults/NULLs.
        with db_conn.cursor() as cur:
            cur.execute(
                "SELECT id, filter_subtitles, file_type, file_size, stage, status FROM job"
            )
            rows = cur.fetchall()
        assert len(rows) == 1
        row_id, filter_subtitles, file_type, file_size, stage, status = rows[0]
        assert str(row_id) == str(pending_job)
        assert filter_subtitles is True
        assert file_type == CONTENT_TYPE
        assert file_size == len(FILE_BODY)
        assert stage == ""
        assert status == "queued"

    def test_job_is_published_to_queue(self, make_client, pending_job, rabbit_channel):
        _confirm(make_client(), pending_job)

        _method, _props, body = rabbit_channel.basic_get(queue=TEST_SETTINGS.job_queue_name, auto_ack=True)
        assert body is not None
        queued = QueuedJob(**json.loads(body))
        assert queued.job_id == pending_job
        assert queued.filterSubtitles is True


class TestConfirmUploadFailsGracefully:
    def test_redis_down(self, make_client, dead_redis_client, pending_job):
        response = _confirm(make_client(redis_=dead_redis_client), pending_job)

        assert response.status_code == 503
        assert "detail" in response.json()

    def test_object_storage_down(self, make_client, dead_s3_client, pending_job):
        response = _confirm(make_client(s3=dead_s3_client), pending_job)

        assert response.status_code == 503
        assert "detail" in response.json()

    def test_job_queue_down(self, make_client, dead_rabbit_channel, pending_job, db_conn):
        response = _confirm(make_client(channel=dead_rabbit_channel), pending_job)

        assert response.status_code == 503
        assert "detail" in response.json()
        with db_conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM job")
            assert cur.fetchone()[0] == 0  # queue publish precedes the DB insert, so no row

    def test_database_down(self, make_client, dead_database_url, pending_job):
        response = _confirm(make_client(database_url=dead_database_url), pending_job)

        assert response.status_code == 503
        assert "detail" in response.json()

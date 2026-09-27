from urllib.parse import urlparse
from uuid import UUID

import pytest

pytestmark = pytest.mark.integration


def _payload(filter_subtitles: bool = False) -> dict:
    return {"filterSubtitles": filter_subtitles, "fileSize": 1024, "fileType": "video/mp4"}


class TestCreateJobStoresPendingJobInRedis:
    @pytest.mark.parametrize("filter_subtitles", [True, False])
    def test_redis_entry_matches_response_and_request(self, make_client, redis_client, filter_subtitles):
        client = make_client()

        response = client.post("/api/v1/job/", json=_payload(filter_subtitles))

        assert response.status_code == 200
        job_id = str(UUID(response.json()["job_id"]))

        stored = redis_client.hgetall(job_id)
        assert set(stored) == {b"presigned_url", b"filterSubtitles"}

        download_url = urlparse(stored[b"presigned_url"].decode())
        assert download_url.scheme in ("http", "https")
        assert download_url.netloc
        assert job_id in download_url.path  # the object key is the job id

        assert bool(int(stored[b"filterSubtitles"])) == filter_subtitles

    def test_only_the_returned_job_id_is_stored(self, make_client, redis_client):
        client = make_client()

        response = client.post("/api/v1/job/", json=_payload())

        assert [k.decode() for k in redis_client.keys("*")] == [response.json()["job_id"]]


class TestCreateJobFailsGracefully:
    def test_redis_down_returns_503(self, make_client, dead_redis_client):
        client = make_client(redis_=dead_redis_client)

        response = client.post("/api/v1/job/", json=_payload())

        assert response.status_code == 503
        assert "detail" in response.json()


import re
from uuid import UUID

import pytest

from backend.api.schemas import MAX_FILE_SIZE_BYTES

VALID_VIDEO_TYPE = "video/mp4"
VALID_AUDIO_TYPE = "audio/mpeg"

# Non audio/video mimetypes that are explicitly allowed
EXCEPTION_MIME_TYPES = [
    "application/ogg",
    "application/mp4",
    "application/x-mpegurl",
    "application/vnd.apple.mpegurl",
    "application/dash+xml",
    "application/x-matroska",
    "application/x-flv",
]


def _job_payload(file_type: str, file_size: int = 1024, filter_subtitles: bool = False) -> dict:
    return {
        "filterSubtitles": filter_subtitles,
        "fileSize": file_size,
        "fileType": file_type,
    }


def _stub_successful_storage(mock_storage, presigned_download_url: str = "https://download.example/signed?sig=abc"):
    mock_storage.create_presigned_upload.return_value = {"url": "https://upload.example", "fields": {}}
    mock_storage.create_presigned_download.return_value = presigned_download_url


class TestFileTypeValidation:
    def test_rejects_string_with_no_forward_slash(self, client, mock_storage, mock_job_cache):
        response = client.post("/api/v1/job/", json=_job_payload("notamimetype"))

        assert response.status_code == 401
        mock_storage.create_presigned_upload.assert_not_called()
        mock_job_cache.save_pending_job.assert_not_called()

    @pytest.mark.parametrize(
        "mime_type",
        ["text/plain", "application/json", "image/png"],
    )
    def test_rejects_single_slash_type_not_video_audio_or_excepted(self, client, mock_storage, mock_job_cache, mime_type):
        response = client.post("/api/v1/job/", json=_job_payload(mime_type))

        assert response.status_code == 415
        mock_storage.create_presigned_upload.assert_not_called()
        mock_job_cache.save_pending_job.assert_not_called()

    @pytest.mark.parametrize("mime_type", EXCEPTION_MIME_TYPES)
    def test_accepts_all_exception_mimetypes(self, client, mock_storage, mock_job_cache, mime_type):
        _stub_successful_storage(mock_storage)

        response = client.post("/api/v1/job/", json=_job_payload(mime_type))

        assert response.status_code == 200

    @pytest.mark.parametrize("mime_type", [VALID_VIDEO_TYPE, VALID_AUDIO_TYPE])
    def test_accepts_standard_audio_and_video_types(self, client, mock_storage, mock_job_cache, mime_type):
        _stub_successful_storage(mock_storage)

        response = client.post("/api/v1/job/", json=_job_payload(mime_type))

        assert response.status_code == 200


class TestFileSizeValidation:
    @pytest.mark.parametrize("file_size", [0, -1])
    def test_rejects_file_size_below_one_byte(self, client, mock_storage, mock_job_cache, file_size):
        response = client.post("/api/v1/job/", json=_job_payload(VALID_VIDEO_TYPE, file_size=file_size))

        assert response.status_code == 422
        mock_storage.create_presigned_upload.assert_not_called()
        mock_job_cache.save_pending_job.assert_not_called()

    def test_rejects_file_size_above_10gb(self, client, mock_storage, mock_job_cache):
        response = client.post(
            "/api/v1/job/", json=_job_payload(VALID_VIDEO_TYPE, file_size=MAX_FILE_SIZE_BYTES + 1)
        )

        assert response.status_code == 422
        mock_storage.create_presigned_upload.assert_not_called()
        mock_job_cache.save_pending_job.assert_not_called()

    @pytest.mark.parametrize("file_size", [1, MAX_FILE_SIZE_BYTES])
    def test_accepts_boundary_file_sizes(self, client, mock_storage, file_size):
        _stub_successful_storage(mock_storage)

        response = client.post("/api/v1/job/", json=_job_payload(VALID_VIDEO_TYPE, file_size=file_size))

        assert response.status_code == 200


class TestJobCacheEntry:
    def test_pending_job_saved_with_presigned_download_url(self, client, mock_storage, mock_job_cache):
        presigned_download_url = "https://vcf-bucket.r2.cloudflarestorage.com/abc123?X-Amz-Signature=deadbeef"
        _stub_successful_storage(mock_storage, presigned_download_url)

        response = client.post(
            "/api/v1/job/", json=_job_payload(VALID_VIDEO_TYPE, filter_subtitles=True)
        )

        assert response.status_code == 200
        returned_job_id = UUID(response.json()["job_id"])

        mock_job_cache.save_pending_job.assert_called_once_with(
            job_id=returned_job_id,
            presigned_url=presigned_download_url,
            filter_subtitles=True,
        )
        # sanity check the value stored in the cache actually looks like a URL
        stored_url = mock_job_cache.save_pending_job.call_args.kwargs["presigned_url"]
        assert re.match(r"^https?://", stored_url)

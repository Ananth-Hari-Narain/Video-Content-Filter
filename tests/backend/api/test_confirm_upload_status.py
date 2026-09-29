from uuid import uuid4

from botocore.exceptions import ClientError

from backend.api.services.job_cache import PendingJob
from backend.api.services.storage import UploadedObjectInfo


def _client_error(code: str) -> ClientError:
    return ClientError(
        error_response={"Error": {"Code": code, "Message": "not found"}},
        operation_name="HeadObject",
    )


class TestJobMissingFromCache:
    def test_returns_404_when_job_not_in_cache(
        self, client, mock_job_cache, mock_storage, mock_job_queue, mock_job_repository
    ):
        job_id = uuid4()
        mock_job_cache.get_pending_job.return_value = None

        response = client.post(f"/api/v1/job/{job_id}/upload_status")

        assert response.status_code == 404
        mock_storage.get_uploaded_object_info.assert_not_called()
        mock_job_queue.publish.assert_not_called()
        mock_job_repository.create_job.assert_not_called()


class TestFileNotYetUploaded:
    def test_returns_404_when_object_not_found(
        self, client, mock_job_cache, mock_storage, mock_job_queue, mock_job_repository
    ):
        job_id = uuid4()
        mock_job_cache.get_pending_job.return_value = PendingJob(
            presigned_url="https://download.example/signed", filter_subtitles=False
        )
        mock_storage.get_uploaded_object_info.side_effect = _client_error("404")

        response = client.post(f"/api/v1/job/{job_id}/upload_status")

        assert response.status_code == 404
        mock_job_queue.publish.assert_not_called()
        mock_job_repository.create_job.assert_not_called()

    def test_returns_404_when_object_missing_no_such_key(
        self, client, mock_job_cache, mock_storage, mock_job_queue, mock_job_repository
    ):
        job_id = uuid4()
        mock_job_cache.get_pending_job.return_value = PendingJob(
            presigned_url="https://download.example/signed", filter_subtitles=True
        )
        mock_storage.get_uploaded_object_info.side_effect = _client_error("NoSuchKey")

        response = client.post(f"/api/v1/job/{job_id}/upload_status")

        assert response.status_code == 404
        mock_job_queue.publish.assert_not_called()
        mock_job_repository.create_job.assert_not_called()


class TestSuccessfulConfirmation:
    def test_publishes_job_to_queue_with_matching_job_id(
        self, client, mock_job_cache, mock_storage, mock_job_queue, mock_job_repository
    ):
        job_id = uuid4()
        presigned_url = "https://download.example/signed?sig=abc"
        mock_job_cache.get_pending_job.return_value = PendingJob(
            presigned_url=presigned_url, filter_subtitles=True
        )
        mock_storage.get_uploaded_object_info.return_value = UploadedObjectInfo(
            file_size=2048, file_type="video/mp4"
        )

        response = client.post(f"/api/v1/job/{job_id}/upload_status")

        assert response.status_code == 200
        mock_job_queue.publish.assert_called_once()
        published_job = mock_job_queue.publish.call_args.args[0]
        assert published_job.job_id == job_id
        assert published_job.download_url == presigned_url
        assert published_job.filterSubtitles is True

    def test_writes_job_to_db_with_correct_job_id_and_file_info(
        self, client, mock_job_cache, mock_storage, mock_job_queue, mock_job_repository
    ):
        job_id = uuid4()
        mock_job_cache.get_pending_job.return_value = PendingJob(
            presigned_url="https://download.example/signed", filter_subtitles=False
        )
        mock_storage.get_uploaded_object_info.return_value = UploadedObjectInfo(
            file_size=4096, file_type="audio/mpeg"
        )

        response = client.post(f"/api/v1/job/{job_id}/upload_status")

        assert response.status_code == 200
        mock_job_repository.create_job.assert_called_once_with(
            job_id=job_id,
            filter_subtitles=False,
            file_type="audio/mpeg",
            file_size=4096,
        )

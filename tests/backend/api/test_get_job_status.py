from uuid import uuid4

from backend.api.schemas import JobStatusResponse


class TestJobExists:
    def test_returns_status_from_repository(self, client, mock_job_repository):
        job_id = uuid4()
        mock_job_repository.get_status.return_value = JobStatusResponse(
            status="Processing", stage="filtering_audio", percent=42
        )

        response = client.get(f"/api/v1/job/{job_id}")

        assert response.status_code == 200
        assert response.json() == {
            "status": "Processing",
            "stage": "filtering_audio",
            "percent": 42,
            "download_link": "",
        }
        mock_job_repository.get_status.assert_called_once_with(job_id)


class TestJobDoesNotExist:
    def test_returns_404_when_job_not_found(self, client, mock_job_repository):
        job_id = uuid4()
        mock_job_repository.get_status.return_value = None

        response = client.get(f"/api/v1/job/{job_id}")

        assert response.status_code == 404
        mock_job_repository.get_status.assert_called_once_with(job_id)

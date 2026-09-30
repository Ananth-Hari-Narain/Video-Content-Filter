import shutil
import uuid

import pika
import pytest

from backend.api.schemas import QueuedJob
from backend.api.services.job_repository import JobRepository
from tests.backend.integration.api.fixtures import TEST_SETTINGS
from backend.config import JOBS_DIR
from backend.worker import handle_message, process_job

from .conftest import needs_media_tools

pytestmark = [pytest.mark.integration, needs_media_tools]


@pytest.fixture
def job_id():
    job_id = uuid.uuid4()
    yield job_id
    shutil.rmtree(JOBS_DIR / str(job_id), ignore_errors=True)


class TestProcessJob:
    def test_video_job_runs_full_pipeline(self, db_conn, mp4_video, download_url, job_id):
        job_repository = JobRepository(connection=db_conn)
        job_repository.create_job(job_id, filter_subtitles=False, file_type="video/mp4", file_size=mp4_video.stat().st_size)
        job = QueuedJob(job_id=job_id, download_url=download_url(mp4_video.name), filterSubtitles=False)

        process_job(job, job_repository)

        output_path = JOBS_DIR / str(job_id) / "output.mp4"
        assert output_path.exists()
        assert output_path.stat().st_size > 0

    def test_audio_job_runs_full_pipeline(self, db_conn, mp3_audio, download_url, job_id):
        job_repository = JobRepository(connection=db_conn)
        job_repository.create_job(job_id, filter_subtitles=False, file_type="audio/mp3", file_size=mp3_audio.stat().st_size)
        job = QueuedJob(job_id=job_id, download_url=download_url(mp3_audio.name), filterSubtitles=False)

        process_job(job, job_repository)

        output_path = JOBS_DIR / str(job_id) / "output.wav"
        assert output_path.exists()
        assert output_path.stat().st_size > 0

    def test_progress_updates_are_written_to_the_db(self, db_conn, mp4_video, download_url, job_id):
        job_repository = JobRepository(connection=db_conn)
        job_repository.create_job(job_id, filter_subtitles=False, file_type="video/mp4", file_size=mp4_video.stat().st_size)
        job = QueuedJob(job_id=job_id, download_url=download_url(mp4_video.name), filterSubtitles=False)

        process_job(job, job_repository)

        record = job_repository.get_status(job_id)
        assert record is not None
        assert record.status == "done"
        assert record.percent == 100


class TestHandleMessage:
    def test_acks_the_message_on_success(self, db_conn, rabbit_channel, mp4_video, download_url, job_id):
        job_repository = JobRepository(connection=db_conn)
        job_repository.create_job(job_id, filter_subtitles=False, file_type="video/mp4", file_size=mp4_video.stat().st_size)
        job = QueuedJob(job_id=job_id, download_url=download_url(mp4_video.name), filterSubtitles=False)
        rabbit_channel.basic_publish(exchange="", routing_key=TEST_SETTINGS.job_queue_name, body=job.model_dump_json())

        method, properties, body = rabbit_channel.basic_get(queue=TEST_SETTINGS.job_queue_name)
        handle_message(rabbit_channel, method, properties, body, job_repository=job_repository)

        assert rabbit_channel.basic_get(queue=TEST_SETTINGS.job_queue_name) == (None, None, None)

    def test_nacks_without_requeue_when_processing_fails(self, db_conn, rabbit_channel, job_id, download_url):
        job_repository = JobRepository(connection=db_conn)
        # No file at this URL - download_job_file will raise, and process_job should propagate.
        job = QueuedJob(job_id=job_id, download_url=download_url("does-not-exist.mp4"), filterSubtitles=False)
        rabbit_channel.basic_publish(exchange="", routing_key=TEST_SETTINGS.job_queue_name, body=job.model_dump_json())

        method, properties, body = rabbit_channel.basic_get(queue=TEST_SETTINGS.job_queue_name)
        handle_message(rabbit_channel, method, properties, body, job_repository=job_repository)

        # requeue=False, so the message is dropped rather than redelivered.
        assert rabbit_channel.basic_get(queue=TEST_SETTINGS.job_queue_name) == (None, None, None)

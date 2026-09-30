import shutil
from pathlib import Path
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


MEDIA_DIR = Path(__file__).parent / "media"
SWEARING_VIDEO = MEDIA_DIR / "swearing.mp4"
CLEAN_VIDEO = MEDIA_DIR / "clean.mp4"


def _needs_file(path: Path):
    return pytest.mark.skipif(not path.exists(), reason=f"{path} not provided")


@pytest.fixture
def serve_media(media_dir, download_url):
    """Copy a long test video next to the media server and return its URL."""
    def _serve(source: Path) -> str:
        shutil.copy(source, media_dir / source.name)
        return download_url(source.name)

    return _serve


@pytest.fixture
def recorded_progress(db_conn, monkeypatch):
    """A real JobRepository whose update_progress calls are also recorded, with a short write interval."""
    monkeypatch.setattr("backend.worker.PROGRESS_UPDATE_INTERVAL_SECONDS", 1)
    repo = JobRepository(connection=db_conn)
    calls = []
    real = repo.update_progress

    def spy(job_id, stage, percent, status="running"):
        calls.append((stage, percent, status))
        real(job_id, stage, percent, status=status)

    repo.update_progress = spy
    return repo, calls


class TestPeriodicProgressUpdates:
    @_needs_file(SWEARING_VIDEO)
    def test_subtitle_filtering_writes_progress_periodically(self, recorded_progress, serve_media, job_id):
        repo, calls = recorded_progress
        repo.create_job(job_id, filter_subtitles=True, file_type="video/mp4", file_size=SWEARING_VIDEO.stat().st_size)
        job = QueuedJob(job_id=job_id, download_url=serve_media(SWEARING_VIDEO), filterSubtitles=True)

        process_job(job, repo)

        running = [(stage, percent) for stage, percent, status in calls if status == "running"]
        assert len({percent for stage, percent in running if stage == "transcribe"}) > 1
        censoring = [percent for stage, percent in running if stage == "censoring video"]
        assert len(censoring) > 1, "expected several writes during the video filtering phase"
        assert censoring == sorted(censoring), "progress must not go backwards"

        stages = [stage for stage, _, _ in calls]
        assert stages.index("transcribe") < stages.index("censoring video") < stages.index("completed")
        assert calls[-1] == ("completed", 100, "done")

        record = repo.get_status(job_id)
        assert (record.status, record.stage, record.percent) == ("done", "completed", 100)

    @_needs_file(CLEAN_VIDEO)
    def test_video_without_swearing_works(self, recorded_progress, serve_media, job_id):
        repo, calls = recorded_progress
        repo.create_job(job_id, filter_subtitles=True, file_type="video/mp4", file_size=CLEAN_VIDEO.stat().st_size)
        job = QueuedJob(job_id=job_id, download_url=serve_media(CLEAN_VIDEO), filterSubtitles=True)

        process_job(job, repo)

        assert calls[-1] == ("completed", 100, "done")

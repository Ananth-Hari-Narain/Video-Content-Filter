from __future__ import annotations

import json
import logging
import subprocess
import time

import pika
import psycopg
import requests

from backend.api.schemas import QueuedJob
from backend.api.services.job_repository import JobRepository
from backend.api.dependencies import get_r2_client
from backend.api.services.storage import R2Storage
from backend.api.settings import load_settings
from backend.config import JOBS_DIR

logger = logging.getLogger(__name__)
MiB = 1024 * 1024
PROGRESS_UPDATE_INTERVAL_SECONDS = 30

def download_job_file(download_url: str, destination) -> None:
    response = requests.get(download_url, stream=True, timeout=30)
    response.raise_for_status()
    with open(destination, "wb") as f:
        # Write to disk megabyte in 10 MiB chunks instead of buffering to memory directly
        # Important for large files
        for chunk in response.iter_content(chunk_size=10 * MiB):
            f.write(chunk)


def probe_file(path) -> dict:
    """Run ffprobe on the downloaded file to make sure it's a well-formed media file."""
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json", "-show_streams", str(path)],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe rejected file: {result.stderr.strip()}")

    probe_info = json.loads(result.stdout)
    if not probe_info.get("streams"):
        raise RuntimeError("ffprobe found no audio/video streams")

    return probe_info


def has_video_stream(probe_info: dict) -> bool:
    return any(stream.get("codec_type") == "video" for stream in probe_info["streams"])


def run_filter_cli(input_path, output_path, has_video: bool, filter_subtitles: bool, on_progress=None) -> None:
    if has_video:
        mode = "full" if filter_subtitles else "audio-only"
        command = ["vcf", "filter-video", str(input_path), "--mode", mode, "-o", str(output_path)]
    else:
        command = ["vcf", "filter-audio", str(input_path), "-o", str(output_path)]
    command.append("--progress-json")

    with subprocess.Popen(command, stdout=subprocess.PIPE, text=True) as process:
        for line in process.stdout:
            try:
                update = json.loads(line)
                stage, percent = update["stage"], int(update["percent"])
            except (ValueError, KeyError, TypeError):
                continue
            if on_progress is not None:
                on_progress(stage, percent)

    if process.returncode != 0:
        raise subprocess.CalledProcessError(process.returncode, command)


def process_job(job: QueuedJob, job_repository: JobRepository, storage: R2Storage) -> None:
    job_dir = JOBS_DIR / str(job.job_id)
    job_dir.mkdir(parents=True, exist_ok=True)
    input_path = job_dir / "input"

    job_repository.update_progress(job.job_id, "downloading", 0, status="running")
    download_job_file(job.download_url, input_path)
    probe_info = probe_file(input_path)
    has_video = has_video_stream(probe_info)
    output_path = job_dir / ("output.mp4" if has_video else "output.wav")

    last_write = None
    last_stage = None

    def report_progress(stage: str, percent: int) -> None:
        nonlocal last_write, last_stage
        now = time.monotonic()
        # Only update database occassionally to prevent db from getting hammered with writes.
        # A change of stage is always written so the transition is never lost.
        if (
            stage == last_stage
            and last_write is not None
            and now - last_write < PROGRESS_UPDATE_INTERVAL_SECONDS
        ):
            return
        last_write = now
        last_stage = stage
        job_repository.update_progress(job.job_id, stage, percent)

    run_filter_cli(
        input_path,
        output_path,
        has_video,
        job.filterSubtitles,
        on_progress=report_progress,
    )

    job_repository.update_progress(job.job_id, "uploading", 100)
    download_link = storage.upload_output(job.job_id, output_path)

    job_repository.update_progress(job.job_id, "completed", 100, status="done", download_link=download_link)
    logger.info("Job %s done, output uploaded as %s", job.job_id, storage.output_key(job.job_id))


def handle_message(channel, method, properties, body, job_repository: JobRepository, storage: R2Storage) -> None:
    try:
        job = QueuedJob.model_validate_json(body)
        logger.info("Picked up job %s", job.job_id)
        process_job(job, job_repository, storage)
        channel.basic_ack(delivery_tag=method.delivery_tag)
    except Exception:
        logger.exception("Failed to process job")
        channel.basic_nack(delivery_tag=method.delivery_tag, requeue=False)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    settings = load_settings()

    storage = R2Storage(client=get_r2_client(), bucket_name=settings.bucket_name)

    def on_message(channel, method, properties, body) -> None:
        # Fresh DB connection per job: a connection held while idle gets dropped by the server/proxy.
        with psycopg.connect(settings.database_url) as db_connection:
            handle_message(channel, method, properties, body, JobRepository(db_connection), storage)

    connection = pika.BlockingConnection(pika.URLParameters(settings.rabbitmq_url))
    channel = connection.channel()
    channel.queue_declare(queue=settings.job_queue_name, durable=True)
    channel.basic_qos(prefetch_count=1)
    channel.basic_consume(
        queue=settings.job_queue_name,
        on_message_callback=on_message,
    )

    logger.info("Worker started, waiting for jobs on %s", settings.job_queue_name)
    try:
        channel.start_consuming()
    except KeyboardInterrupt:
        channel.stop_consuming()
    finally:
        connection.close()


if __name__ == "__main__":
    main()

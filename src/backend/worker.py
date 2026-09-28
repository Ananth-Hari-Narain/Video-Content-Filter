"""Worker process: pulls queued jobs from RabbitMQ and runs the filtering CLI on them.

For now this does not touch the database or upload results anywhere - it just
downloads the file, sanity-checks it with ffprobe, and runs `vcf` on it.
"""

from __future__ import annotations

import json
import logging
import subprocess
import time
from functools import partial

import pika
import psycopg
import requests

from backend.api.schemas import QueuedJob
from backend.api.services.job_repository import JobRepository
from backend.api.settings import load_settings
from backend.config import JOBS_DIR

logger = logging.getLogger(__name__)
MiB = 1024 * 1024
PROGRESS_UPDATE_INTERVAL_SECONDS = 30

def download_job_file(download_url: str, destination) -> None:
    response = requests.get(download_url, stream=True, timeout=30)
    response.raise_for_status()
    with open(destination, "wb") as f:
        # Write to disk megabyte in 10 MiB chunksinstead of buffering to memory directly
        # Important for large files
        for chunk in response.iter_content(chunk_size=10 * MiB):
            f.write(chunk)


def probe_file(path) -> dict:
    """Run ffprobe on the downloaded file to make sure it's a well-formed media file.

    ffprobe will fail or hang on garbage/malicious input, so a clean, quick run with
    at least one audio/video stream is treated as a proxy for "safe to process".
    """
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


def process_job(job: QueuedJob, job_repository: JobRepository) -> None:
    job_dir = JOBS_DIR / str(job.job_id)
    job_dir.mkdir(parents=True, exist_ok=True)
    input_path = job_dir / "input"
    output_path = job_dir / "output"

    download_job_file(job.download_url, input_path)
    probe_info = probe_file(input_path)

    last_write = None

    def report_progress(stage: str, percent: int) -> None:
        nonlocal last_write
        now = time.monotonic()
        # Only update database occassionally to prevent db from getting hammered with writes
        if last_write is not None and now - last_write < PROGRESS_UPDATE_INTERVAL_SECONDS:
            return
        last_write = now
        job_repository.update_progress(job.job_id, stage, percent)

    run_filter_cli(
        input_path,
        output_path,
        has_video_stream(probe_info),
        job.filterSubtitles,
        on_progress=report_progress,
    )

    logger.info("Job %s done, output at %s", job.job_id, output_path)


def handle_message(channel, method, properties, body, job_repository: JobRepository) -> None:
    try:
        job = QueuedJob.model_validate_json(body)
        logger.info("Picked up job %s", job.job_id)
        process_job(job, job_repository)
        channel.basic_ack(delivery_tag=method.delivery_tag)
    except Exception:
        logger.exception("Failed to process job")
        channel.basic_nack(delivery_tag=method.delivery_tag, requeue=False)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    settings = load_settings()

    db_connection = psycopg.connect(settings.database_url)
    job_repository = JobRepository(connection=db_connection)

    connection = pika.BlockingConnection(pika.URLParameters(settings.rabbitmq_url))
    channel = connection.channel()
    channel.queue_declare(queue=settings.job_queue_name, durable=True)
    channel.basic_qos(prefetch_count=1)
    channel.basic_consume(
        queue=settings.job_queue_name,
        on_message_callback=partial(handle_message, job_repository=job_repository),
    )

    logger.info("Worker started, waiting for jobs on %s", settings.job_queue_name)
    try:
        channel.start_consuming()
    except KeyboardInterrupt:
        channel.stop_consuming()
    finally:
        connection.close()
        db_connection.close()


if __name__ == "__main__":
    main()

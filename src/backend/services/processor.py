from __future__ import annotations

from argparse import Namespace
from pathlib import Path

from cli import cli

from backend.api.schemas import JobStatus
from backend.services.job_store import job_store


def process_job(job_id: str) -> None:
    record = job_store.get(job_id)
    if record is None:
        return

    try:
        job_store.set_status(job_id, JobStatus.processing)

        if record.media_type.value == "audio":
            args = Namespace(
                input=str(record.input_path),
                output=str(record.output_path),
                keep_temp=False,
            )
            cli._run_filter_audio(args)
        else:
            args = Namespace(
                input=str(record.input_path),
                mode=record.mode.value,
                output=str(record.output_path),
                keep_temp=False,
            )
            cli._run_filter_video(args)

        if not Path(record.output_path).exists():
            raise RuntimeError("Filtering completed but output file was not found.")

        job_store.set_status(job_id, JobStatus.completed)
    except Exception as exc:  # noqa: BLE001
        job_store.set_status(job_id, JobStatus.failed, error=str(exc))

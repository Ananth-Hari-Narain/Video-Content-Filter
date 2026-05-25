import argparse
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import cv2
import numpy as np

from content_filter.audio import AudioCensorer
from content_filter.utils import get_relative_character_widths, load_profanity
from content_filter.video import *


def _default_profanity_path() -> str:
    return str(Path(__file__).resolve().parents[1] / "content_filter" / "config" / "profanity_words.txt")


def _load_default_profanity_set(tmpdir: str):
    return load_profanity(_default_profanity_path(), tmpdir)


def _default_audio_output_path(input_path: str) -> str:
    source = Path(input_path)
    return str(source.with_name(f"{source.stem}_censored.wav"))


def _default_video_output_path(input_path: str, mode: str) -> str:
    source = Path(input_path)
    suffix = "full_censored" if mode == "full" else "audio_censored"
    return str(source.with_name(f"{source.stem}_{suffix}.mp4"))


def _ensure_parent(path: str) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)


def _run_filter_audio(args) -> int:
    output_path = args.output or _default_audio_output_path(args.input)
    _ensure_parent(output_path)

    tmpdir = tempfile.mkdtemp(prefix="video-content-filter-")
    should_cleanup_tmp = not args.keep_temp

    try:
        censorer = AudioCensorer()
        profanity_set = _load_default_profanity_set(tmpdir)
        _, result_path = censorer.censor_audio_file(
            audio_path=args.input,
            profanity_set=profanity_set,
            output_path=output_path,
            tmpdir=tmpdir,
        )
    finally:
        if should_cleanup_tmp and os.path.isdir(tmpdir):
            shutil.rmtree(tmpdir)

    print("Done! Audio saved at:", result_path)
    return 0


def _run_filter_video(args) -> int:
    output_path = args.output or _default_video_output_path(args.input, args.mode)
    _ensure_parent(output_path)

    tmpdir = tempfile.mkdtemp(prefix="video-content-filter-")
    should_cleanup_tmp = not args.keep_temp

    try:
        censorer = AudioCensorer()
        profanity_set = _load_default_profanity_set(tmpdir)
        bad_word_timestamps, censored_audio_path = censorer.censor_audio_from_video(
            video_path=args.input,
            profanity_set=profanity_set,
            output_folder=tmpdir,
            tmpdir=tmpdir,
        )

        if args.mode == "audio-only" or not bad_word_timestamps:
            remux_video_audio(args.input, censored_audio_path, output_path)
        else:
            quad_map, fps, (width, height), n = get_bounding_quads(
                args.input,
                bad_word_timestamps,
                get_relative_character_widths(),
            )
            # get_bounding_quads returns int frame keys; keep ints for fast lookup.
            quad_map = {int(k): v for k, v in quad_map.items()}
            masked_video_path = os.path.join(tmpdir, "masked_video.mp4")
            render_censored_video(args.input, masked_video_path, quad_map, fps, width, height, n)
            remux_video_audio(masked_video_path, censored_audio_path, output_path)
    finally:
        if should_cleanup_tmp and os.path.isdir(tmpdir):
            shutil.rmtree(tmpdir)

    print("Done! Video saved at:", output_path)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="vcf",
        description="Filter profanity from audio and video files.",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    audio_cmd = subparsers.add_parser(
        "filter-audio",
        help="Censor profanity in an audio file.",
    )
    audio_cmd.add_argument("input", help="Input audio file path.")
    audio_cmd.add_argument(
        "-o",
        "--output",
        help="Output audio path. Defaults to [audio_name]_censored.wav.",
    )
    audio_cmd.add_argument(
        "--keep-temp",
        action="store_true",
        help="Keep temporary files when an auto-created temp directory is used.",
    )
    audio_cmd.set_defaults(handler=_run_filter_audio)

    video_cmd = subparsers.add_parser(
        "filter-video",
        help="Censor profanity in a video file.",
    )
    video_cmd.add_argument("input", help="Input video file path.")
    video_cmd.add_argument(
        "--mode",
        required=True,
        choices=["full", "audio-only"],
        help="Fully redacts on-screen profanity and bleeps audio; audio-only bleeps audio only.",
    )
    video_cmd.add_argument(
        "-o",
        "--output",
        help="Output video path. Defaults to mode-based [video_name]_*_censored.mp4.",
    )
    video_cmd.add_argument(
        "--keep-temp",
        action="store_true",
        help="Keep temporary files when an auto-created temp directory is used.",
    )
    video_cmd.set_defaults(handler=_run_filter_video)

    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.handler(args)

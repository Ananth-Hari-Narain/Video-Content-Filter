import shutil
import subprocess

import pytest

from backend.worker import has_video_stream, probe_file

pytestmark = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="ffmpeg/ffprobe not installed",
)

VIDEO_INPUT = ["-f", "lavfi", "-i", "testsrc=duration=1:size=64x64:rate=10"]
AUDIO_INPUT = ["-f", "lavfi", "-i", "sine=frequency=440:duration=1"]


def _ffmpeg(path, *args):
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", *args, str(path)],
        check=True,
        capture_output=True,
    )
    return path


@pytest.fixture(scope="module")
def media_dir(tmp_path_factory):
    return tmp_path_factory.mktemp("media")


@pytest.fixture(scope="module")
def mp4_video(media_dir):
    """Standard video: H.264 + AAC in an MP4 container."""
    return _ffmpeg(
        media_dir / "video.mp4",
        *VIDEO_INPUT, *AUDIO_INPUT, "-c:v", "libx264", "-c:a", "aac", "-shortest",
    )


@pytest.fixture(scope="module")
def mp3_audio(media_dir):
    """Standard audio: MP3."""
    return _ffmpeg(media_dir / "audio.mp3", *AUDIO_INPUT, "-c:a", "libmp3lame")


@pytest.fixture(scope="module")
def flv_video(media_dir):
    """Flash video container."""
    return _ffmpeg(
        media_dir / "video.flv",
        *VIDEO_INPUT, *AUDIO_INPUT, "-c:v", "flv", "-c:a", "mp3", "-shortest",
    )


@pytest.fixture(scope="module")
def ogg_audio(media_dir):
    """Ogg container holding only Vorbis audio."""
    return _ffmpeg(media_dir / "audio.ogg", *AUDIO_INPUT, "-c:a", "libvorbis")


@pytest.fixture(scope="module")
def ogg_video(media_dir):
    """Ogg container holding Theora video + Vorbis audio (same container as ogg_audio)."""
    return _ffmpeg(
        media_dir / "video.ogv",
        *VIDEO_INPUT, *AUDIO_INPUT, "-c:v", "libtheora", "-c:a", "libvorbis", "-shortest",
    )


def _streams(probe_info):
    return {s["codec_type"] for s in probe_info["streams"]}


class TestProbeFile:
    def test_video_file_is_detected_as_video(self, mp4_video):
        assert _streams(probe_file(mp4_video)) == {"video", "audio"}

    def test_audio_file_is_detected_as_audio(self, mp3_audio):
        assert _streams(probe_file(mp3_audio)) == {"audio"}

    @pytest.mark.parametrize("extension", [".pdf", ".json", ".zip", ""])
    def test_non_media_extension_and_non_media_content_is_rejected(self, tmp_path, extension):
        path = tmp_path / f"notes{extension}"
        path.write_text("just some plain text, definitely not media\n" * 50)

        with pytest.raises(RuntimeError, match="ffprobe rejected file"):
            probe_file(path)

    @pytest.mark.parametrize("extension", [".mp4", ".mp3", ".mkv", ".wav", ".flv"])
    def test_media_extension_with_non_media_content_is_rejected(self, tmp_path, extension):
        path = tmp_path / f"fake{extension}"
        path.write_text("this is not really a media file\n" * 50)

        with pytest.raises(RuntimeError, match="ffprobe rejected file"):
            probe_file(path)

    def test_media_content_with_misleading_extension_is_still_detected(self, mp4_video, tmp_path):
        renamed = tmp_path / "video.txt"
        shutil.copy(mp4_video, renamed)

        assert "video" in _streams(probe_file(renamed))

    def test_file_with_no_extension_is_probed_by_content(self, mp4_video, tmp_path):
        """The worker saves downloads as a bare 'input' file."""
        bare = tmp_path / "input"
        shutil.copy(mp4_video, bare)

        assert "video" in _streams(probe_file(bare))

    def test_empty_file_is_rejected(self, tmp_path):
        path = tmp_path / "empty.mp4"
        path.touch()

        with pytest.raises(RuntimeError):
            probe_file(path)

    def test_missing_file_is_rejected(self, tmp_path):
        with pytest.raises(RuntimeError, match="ffprobe rejected file"):
            probe_file(tmp_path / "does_not_exist.mp4")


class TestHasVideoStream:
    def test_standard_video_format(self, mp4_video):
        assert has_video_stream(probe_file(mp4_video)) is True

    def test_standard_audio_format(self, mp3_audio):
        assert has_video_stream(probe_file(mp3_audio)) is False

    def test_flash_video(self, flv_video):
        assert has_video_stream(probe_file(flv_video)) is True

    def test_ogg_container_with_only_audio(self, ogg_audio):
        assert has_video_stream(probe_file(ogg_audio)) is False

    def test_ogg_container_with_video(self, ogg_video):
        assert has_video_stream(probe_file(ogg_video)) is True

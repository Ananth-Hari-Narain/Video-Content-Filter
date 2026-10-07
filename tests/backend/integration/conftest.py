import functools
import http.server
import shutil
import subprocess
import threading

import pytest

needs_media_tools = pytest.mark.skipif(
    shutil.which("vcf") is None or shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="vcf/ffmpeg/ffprobe not installed",
)


def _ffmpeg(path, *args):
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", *args, str(path)],
        check=True,
        capture_output=True,
    )
    return path


@pytest.fixture(scope="session")
def media_dir(tmp_path_factory):
    return tmp_path_factory.mktemp("worker_media")


@pytest.fixture(scope="session")
def media_server(media_dir):
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(media_dir))
    server = http.server.ThreadingHTTPServer(("localhost", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server
    server.shutdown()
    thread.join()


@pytest.fixture
def download_url(media_server):
    def _url(filename: str) -> str:
        return f"http://localhost:{media_server.server_port}/{filename}"

    return _url


@pytest.fixture(scope="session")
def mp4_video(media_dir):
    """Standard video: H.264 + AAC in an MP4 container, placed where media_server can serve it."""
    return _ffmpeg(
        media_dir / "video.mp4",
        "-f", "lavfi", "-i", "testsrc=duration=1:size=64x64:rate=10",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
        "-c:v", "libx264", "-c:a", "aac", "-shortest",
    )


@pytest.fixture(scope="session")
def mp3_audio(media_dir):
    """Standard audio: MP3, placed where media_server can serve it."""
    return _ffmpeg(
        media_dir / "audio.mp3",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
        "-c:a", "libmp3lame",
    )

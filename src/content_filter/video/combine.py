import cv2
import subprocess
import numpy as np

def remux_video_audio(video_path: str, audio_path: str, output_path: str) -> None:
    command = [
        "ffmpeg",
        "-y",
        "-i",
        video_path,
        "-i",
        audio_path,
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        "-map",
        "0:v:0",
        "-map",
        "1:a:0",
        output_path,
    ]
    subprocess.run(command, check=True)


def render_censored_video(video_path: str, censored_video_path: str, quad_map: dict, fps: float, width: int, height: int, n: int) -> None:
    cap = cv2.VideoCapture(video_path)
    out = cv2.VideoWriter(censored_video_path, cv2.VideoWriter.fourcc(*"mp4v"), fps, (width, height))

    idx = 0
    ordered_frames = sorted(int(frame_idx) for frame_idx in quad_map.keys())
    while True:
        ret, frame = cap.read()
        if not ret:
            break

        for frame_idx in ordered_frames:
            if frame_idx <= idx < frame_idx + n:
                for quad in quad_map.get(frame_idx, []):
                    cv2.fillConvexPoly(frame, np.array(quad, dtype=np.int32), (0, 0, 0))
                break

        out.write(frame)
        idx += 1

    cap.release()
    out.release()
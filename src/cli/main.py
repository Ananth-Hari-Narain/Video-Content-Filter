import cv2
from content_filter.video import get_bounding_quads
from content_filter.audio import *
from content_filter.utils import *
import os.path
import numpy as np
import json
import subprocess
from pathlib import Path

if __name__ == "__main__":
    PROJECT_ROOT = Path(__file__).resolve().parents[2]
    VIDEO_PATH = str(PROJECT_ROOT / "data/raw/example1.mp4")
    PROFANITY_PATH = str(PROJECT_ROOT / "src/content_filter/config/profanity_words.txt")
    OUTPUT_PATH = str(PROJECT_ROOT / "data/processed")
    TMP_DIR = str(PROJECT_ROOT / "src/tmp")
    # Filter audio for transcription
    bad_word_timestamps, censored_audio_path = censor_audio_from_video(VIDEO_PATH, load_profanity(PROFANITY_PATH, TMP_DIR), OUTPUT_PATH, TMP_DIR)
    transcription_path = os.path.join(TMP_DIR, "transcription.json")
    if not bad_word_timestamps:
        print("No profanity detected: video unmodified")
    else:
        # Filtering the video
        test_path = "/home/ananth/repos/video-content-filter/src/tmp/results.json"
        print("Identifying profanity on screen...")
        if not os.path.exists(test_path):
            quad_map, fps, (w, h), n = get_bounding_quads(VIDEO_PATH, bad_word_timestamps, get_relative_character_widths())
            with open(os.path.join(TMP_DIR, "results.json"), 'w') as fp:
                json.dump(quad_map, fp, indent=2)
        else:
            with open(test_path, 'r') as file:
                quad_map = json.load(file)
            fps = 30
            w = 1350
            h = 772
            n = 3
        
        censored_video_path = os.path.join(TMP_DIR, "out.mp4")
        
        print("On-screen profanity identified! Drawing censoring boxes in...")
        cap = cv2.VideoCapture(VIDEO_PATH)
        out = cv2.VideoWriter(censored_video_path, cv2.VideoWriter.fourcc(*'mp4v'), fps, (w, h))
        idx = 0
        ordered_frames = sorted(quad_map.keys())
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            
            for frame_idx in ordered_frames:
                if int(frame_idx) <= idx < int(frame_idx) + n:
                    for quad in quad_map.get(frame_idx, []):
                        cv2.fillConvexPoly(frame, np.array(quad, dtype=np.int32), (0, 0, 0))
                    break
            
            out.write(frame)
            idx += 1
        cap.release()
        out.release()

        print("Video created! Combining video and audio...")
        # Combining the video and audio
        final_output_path = os.path.join(OUTPUT_PATH, "censored.mp4")
        command = ['ffmpeg', 
                   '-i', censored_video_path, 
                   '-i', censored_audio_path, 
                   '-c:v', 'copy', '-c:a', 'aac', '-map', '0:v:0', '-map', '1:a:0', 
                   final_output_path]
        subprocess.run(command, check=True)
        print("Done! Video saved at: ", final_output_path)
        

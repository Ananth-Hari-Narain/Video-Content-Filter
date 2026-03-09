from pathlib import Path
import subprocess
import os
import json
import whisper
import soundfile as sf
import numpy as np
from content_filter.utils import *

def censor_audio_from_video(video_path: str, profanity_set: set[str], output_folder: str, tmpdir="temp", debug_output_on: bool = True):
    # Create temporary directory
    create_new_file_if_missing(tmpdir, os.mkdir, tmpdir)

    if debug_output_on:
        print("Temp file created!")

    # Extract audio
    audio_path = os.path.join(tmpdir, "extracted_audio.wav")
    create_new_file_if_missing(audio_path, _extract_from_video, video_path, audio_path)
    if debug_output_on:
        print("Audio extracted!")

    # Save transcription as a json
    transcription_path = os.path.join(tmpdir, "transcription.json")
    create_new_file_if_missing(transcription_path, _transcribe_audio, audio_path, transcription_path)
    if debug_output_on:
        print("Transcription generated!")

    # As this is a fairly fast process, we don't need the file "checkpoints" from before
    bad_word_timestamps = _identify_profanity(transcription_path, profanity_set)
    new_audio_path = _apply_bleep_at_timestamps(audio_path, bad_word_timestamps, output_folder)
    cleanup_audio(Path(tmpdir))
    return bad_word_timestamps, new_audio_path

def _extract_from_video(video_path, output_file, sample_rate=16000):
    """
    Extract audio from video, returning a path to the audio file.
    """
    # FFmpeg command to extract audio
    command = [
        "ffmpeg",
        "-i", video_path,          # input file
        "-vn",                     # ignore video
        "-ac", "1",                # mono audio
        "-ar", str(sample_rate),   # sample rate
        output_file                # output file
    ]

    subprocess.run(command, check=True)

def _transcribe_audio(audio_file, output_path, model_name="small"):
    """
    Use openai whisper to create transcription, storing it as a json.
    Returns path to json.
    """
    model = whisper.load_model(model_name)
    transcription = model.transcribe(audio_file, word_timestamps=True, verbose=False)

    tmp_output_path = f"{output_path}.tmp"
    with open(tmp_output_path, "w", encoding="utf-8") as file:
        json.dump(transcription, file, indent=1)
    os.replace(tmp_output_path, output_path)

    return output_path

def _identify_profanity(transcription_path, profanity_set):
    """
    Returns word-timestamps pairs (and probability of correct transcription).
    No file paths here.
    """
    with open(transcription_path) as file:
        transcription = json.load(file)

    profanities = []
    for seg in transcription['segments']:
        # Note to self: will likely generate false positives as i am not looking at probability.
        for wordStamp in seg['words']:
            word = clean_word(wordStamp['word'])
            if word in profanity_set:
                profanities.append(wordStamp)

    return profanities

def _apply_bleep_at_timestamps(audio_file, bad_word_timestamps, output_folder):
    """
    Takes a list of timestamps and audio and applies a "bleep" sound effect to
    the audio.
    """
    # Format of bad_word_timestamps: list of dictionaries 
    # with keys 'word', 'start', 'end', 'probability'
    bleep_freq: int = 1000
    bleep_volume: float = 0.5

    audio, sample_rate = sf.read(audio_file)
    # Handle mono or stereo
    if audio.ndim == 1:
        audio = audio[:, None]

    censored_audio = audio.copy()

    for timestamp in bad_word_timestamps:
        start = timestamp['start']
        end = timestamp['end']

        start_sample = int(start * sample_rate)
        end_sample = int(end * sample_rate)

        duration = end_sample - start_sample
        t = np.linspace(0, duration / sample_rate, duration, False)

        # Generate bleep tone
        bleep = bleep_volume * np.sin(2 * np.pi * bleep_freq * t)

        # Match channels
        bleep = np.tile(bleep[:, None], (1, censored_audio.shape[1]))

        censored_audio[start_sample:end_sample] = bleep

    # Save output
    output_file = os.path.join(output_folder, "censored_audio.wav")
    sf.write(output_file, censored_audio, sample_rate)
    return output_file


# Not 'hidden' as I might need this if CLI needs to manually clean up.
def cleanup_audio(temp_folder: Path):
    """
    Removes temporary files used for audio extraction process
    """
    remove_files = [
        "extracted_audio.wav"
    ]

    for file_path in temp_folder.iterdir():
        if file_path.is_file() and file_path.name in remove_files:
            file_path.unlink()
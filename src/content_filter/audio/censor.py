from pathlib import Path
import subprocess
import os.path
from shutil import rmtree
import json
import whisper
import re
import soundfile as sf
import numpy as np
from content_filter.utils import create_new_file_if_missing

def censor_audio_from_video(video_path: str, profanity_path: str, output_folder: str, debug_output_on: bool = True):
    # Create temporary directory
    tmpdir = "temp"
    create_new_file_if_missing(tmpdir, os.mkdir, tmpdir)

    if debug_output_on:
        print("Temp file created!")

    # Extract audio
    audio_path = os.path.join(tmpdir, "extracted_audio.wav")
    create_new_file_if_missing(audio_path, _extract_from_video, video_path, audio_path)
    if debug_output_on:
        print("Audio extracted!")
    
    # Load profanity set (note that no new file is created.)
    profanity_set = _load_profanity(profanity_path, tmpdir)
    if debug_output_on:
        print("Profanity set loaded!")

    # Save transcription as a json
    transcription_path = os.path.join(tmpdir, "transcription.json")
    create_new_file_if_missing(transcription_path, _transcribe_audio, audio_path, transcription_path)
    if debug_output_on:
        print("Transcription generated!")

    # As this is a fairly fast process, we don't need the file "checkpoints" from before
    bad_word_timestamps = _identify_profanity(transcription_path, profanity_set)
    new_audio_path = _apply_bleep_at_timestamps(audio_path, bad_word_timestamps, output_folder)
    cleanup_audio(Path(tmpdir))
    return new_audio_path

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

def _load_profanity(profanity_path, tmpdir):
    """
    Load the list of profanity words from a file, returning a set.
    """
    profanity_set = set()
    with open(profanity_path, "r", encoding="utf-8") as f:
        for line in f:
            word = line.strip().lower()
            profanity_set.add(word)
    
    return profanity_set

def _transcribe_audio(audio_file, output_path, model_name="small"):
    """
    Use openai whisper to create transcription, storing it as a json.
    Returns path to json.
    """
    model = whisper.load_model(model_name)
    with open(output_path, "w") as file:
        json.dump(model.transcribe(audio_file, word_timestamps=True), file)

    return output_path

def _remove_punctuation(text: str) -> str:
    return re.sub(r"[^\w\s]", "", text)

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
            word = _remove_punctuation(wordStamp['word'].strip()).lower()
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


# Not 'hidden' as I might need this if CLI needs to manually clean up.
def cleanup_audio(temp_folder: Path):
    """
    Removes temporary files used for audio extraction process
    """
    ## Check temp folder has word temp in it (mostly for testing, as real application, this should be deleted automatically)
    if (temp_folder.name == "temp"):
        rmtree(temp_folder)
    else:
        raise FileNotFoundError(f"Folder you are trying to delete is named {temp_folder.name}. Are you sure you want to delete it?")
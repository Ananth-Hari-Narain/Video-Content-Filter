# Video-Content-Filter
A program that can filter out foul language in both the audio and visual parts of the video

## CLI

Install the package in editable mode:

```bash
pip install -e .
```

Run command help:

```bash
video-content-filter --help
```

### Filter audio

```bash
video-content-filter filter-audio input.wav
video-content-filter filter-audio input.wav --output output.wav
```

- Input: any audio file supported by the current pipeline
- Output default (when omitted): `[audio_file_name]_censored.wav`

### Filter video

```bash
video-content-filter filter-video input.mp4 --mode audio-only
video-content-filter filter-video input.mp4 --mode full --output final.mp4
```

- `--mode audio-only`: only censors spoken profanity in audio and keeps video pixels unchanged
- `--mode full`: censors spoken profanity in audio and masks detected on-screen profanity

Video output defaults (when omitted):
- `audio-only`: `[video_name]_audio_censored.mp4`
- `full`: `[video_name]_full_censored.mp4`

Optional extraction of censored audio while filtering video:

```bash
video-content-filter filter-video input.mp4 --mode full
video-content-filter filter-video input.mp4 --mode audio-only
```


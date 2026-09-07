FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml requirements.txt ./
COPY src/ ./src/
COPY src/content_filter/config/profanity_words.txt ./src/content_filter/config/profanity_words.txt

RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir .

# Pre-bake model weights so containers start without needing network access.
RUN python -c "from faster_whisper import WhisperModel; WhisperModel('small')"
RUN python -c "import easyocr; easyocr.Reader(['en'])"

ENV PYTHONPATH=/app/src

EXPOSE 8000

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]

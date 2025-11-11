FROM python:3.11-slim

WORKDIR /app

# Install system dependencies: ffmpeg for video generation, fonts for text overlay
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    ffmpeg \
    fonts-dejavu \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY src /app/src

ENV IMAGE_URL="https://kunde.byggekamera.no/?u=nytt-sykehus-aker&c=1059"
ENV INTERVAL_SECONDS=300
ENV STORAGE_DIR=/data/images
ENV MAX_FILES=0
ENV MAX_AGE_DAYS=0
ENV TIMEOUT_SECONDS=15
ENV RETRY_COUNT=3

EXPOSE 5000

VOLUME ["/data"]

CMD ["python", "-u", "src/fetcher.py"]

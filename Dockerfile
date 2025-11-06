FROM python:3.11-slim

WORKDIR /app

# system deps for requests if needed (kept minimal)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY src /app/src

ENV IMAGE_URL=""
ENV INTERVAL_SECONDS=300
ENV STORAGE_DIR=/data/images
ENV MAX_FILES=0
ENV MAX_AGE_DAYS=0
ENV TIMEOUT_SECONDS=15
ENV RETRY_COUNT=3

VOLUME ["/data"]

CMD ["python", "-u", "src/fetcher.py"]

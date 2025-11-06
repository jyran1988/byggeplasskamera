# Image Fetcher

Small, lightweight image fetcher that periodically downloads an image from a
URL and stores it on disk. Designed to run on a Debian laptop in Docker for
long-lived operation.

Features:
- Configurable via environment variables
- Retention by max files or max age
- Retries with backoff
- Keeps a `latest` symlink/file for easy access

Files added:
- `src/fetcher.py` - main fetcher script
- `Dockerfile` - container image
- `docker-compose.yml` - example compose
- `config.example.env` - example env file
- `.github/workflows/ci.yml` - CI template

Quick start (docker):

1. Build image:

```
docker build -t image-fetcher:latest .
```

2. Run with a local volume for images:

```
docker run -d --name image-fetcher \
  -e IMAGE_URL="https://example.com/camera.jpg" \
  -e INTERVAL_SECONDS=300 \
  -v /path/to/store:/data \
  --restart unless-stopped \
  image-fetcher:latest
```

Systemd example (deploy on Debian without Docker):

1. Create a small virtualenv and run the script. Or use the container. If using
   the script directly, create a unit file like `/etc/systemd/system/image-fetcher.service`:

```
[Unit]
Description=Image fetcher
After=network-online.target

[Service]
User=someuser
WorkingDirectory=/opt/image-fetcher
EnvironmentFile=/opt/image-fetcher/config.env
ExecStart=/usr/bin/python3 /opt/image-fetcher/src/fetcher.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Reliability notes for a 2-year run:
- Use a bind-mounted persistent volume (e.g. external HDD or SSD) for `/data`.
- Use Docker `--restart unless-stopped` or systemd `Restart=always` so crashes restart.
- Monitor disk usage; configure `MAX_FILES` or `MAX_AGE_DAYS` to limit storage.
- Consider rotating or syncing images offsite (rsync or rclone) periodically.
- Keep host updated; consider unattended-upgrades and power-fail measures.

CI/CD:
- The included GitHub Actions workflow builds the container and runs a quick import
  test. To push images, add steps and registry secrets (GHCR, Docker Hub, etc.).

Configuration environment variables (see `config.example.env`):
- IMAGE_URL - required URL to fetch
- INTERVAL_SECONDS - seconds between fetches
- STORAGE_DIR - where images are stored (container: /data)
- MAX_FILES - max number of stored files (0 disabled)
- MAX_AGE_DAYS - max age in days (0 disabled)
- TIMEOUT_SECONDS - HTTP timeout
- RETRY_COUNT - number of retries on error

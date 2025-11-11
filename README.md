# Byggeplass Kamera - Image Fetcher & Timelapse# Image Fetcher



Lightweight system to periodically fetch images from a camera/webcam URL, store them on disk, serve them via a web interface, and generate timelapse videos with timestamps.Small, lightweight image fetcher that periodically downloads an image from a

URL and stores it on disk. Designed to run on a Debian laptop in Docker for

Designed to run on a Debian laptop via Docker for long-term operation (2+ years).long-lived operation.



## FeaturesFeatures:

- Configurable via environment variables

- **Image Fetcher**: periodically downloads images from a URL with configurable interval, retries, and storage retention- Retention by max files or max age

- **Web Server**: serves the latest image, lists all images for download, and provides a health check endpoint- Retries with backoff

- **Timelapse Generator**: creates MP4 videos from a range of images with optional filename overlay in bottom-left corner- Keeps a `latest` symlink/file for easy access

- **Configurable**: all settings via environment variables

- **Reliable**: restart policies, atomic file writes, disk retention policiesFiles added:

- `src/fetcher.py` - main fetcher script

## Quick Start with Docker Compose- `Dockerfile` - container image

- `docker-compose.yml` - example compose

1. Navigate to the repository:- `config.example.env` - example env file

`.github/workflows/ci.yml` - CI template

cd /path/to/byggeplasskamera

## Quick usage (if setup is okay)

2. Create the data directory:1. Log into the server (SSH or local).

```bash
ssh julius@192.168.86.158
``` 
- enter password

2. verify running docker containers:

  - ```docker ps```

3. Navigate to image fetcher directory:

```bash
cd /var/lib/docker/volumes/byggeplasskamera_images/_data/images
```

  - ```dir``` to se all files

4. (Optional) Repo for application:
```bash
cd /opt/git/byggeplasskamera
```

```bash
docker compose up -d
```

- (to run container, envs in compose file)

5. Generate timelapse video 
 - via enpoint sync
 ```bash
 curl -X POST 'http://localhost/timelapse' -d 'fps=30' -d 'no_overlay=1'
# returns when done: {"status":"finished","output_path":"/data/images/timelapse_20251111_213501.mp4"}
 ```
 - via endpoint async
  ```bash
  curl -X POST 'http://host/timelapse?async=true&fps=30'
# -> {"job_id":"...","status":"queued","output_path":"/data/images/timelapse_...mp4"}
curl http://host/timelapse/<job_id>  # check status
```
 - (inside container):
```bash
docker exec -it byggeplasskamera-web-1 python src/timelapse.py /data/images -o /data/timelapse.mp4 --fps 30
```

This will start:

- **fetcher** service: downloads images every 300 seconds## Quick start (docker)

- **web** service: serves images on port 80

1. Build image:

Check status:

``` bash
docker compose psdocker build -t image-fetcher:latest .

docker compose logs -f fetcher

docker compose logs -f web
```

2. Run with a local volume for images:



## Web Server Endpoints

docker run -d --name image-fetcher \

Access the web interface at `http://your-debian-server/`:  -e IMAGE_URL="https://example.com/camera.jpg" \

  -e INTERVAL_SECONDS=300 \

- **`/`** → redirects to `/latest`  -v /path/to/store:/data \

- **`/latest`** → serves the newest image  --restart unless-stopped \

- **`/list`** → JSON list of all images  image-fetcher:latest

- **`/download/<filename>`** → download a specific image```

- **`/health`** → health check

Systemd example (deploy on Debian without Docker):

Examples:

```bash1. Create a small virtualenv and run the script. Or use the container. If using

# View latest image in browser   the script directly, create a unit file like `/etc/systemd/system/image-fetcher.service`:

http://192.168.1.100/latest

```

# Get JSON list of images[Unit]

curl http://192.168.1.100/list | jq .Description=Image fetcher

After=network-online.target

# Download a specific image

curl -O http://192.168.1.100/download/20250101_120000.jpg[Service]

```User=someuser

WorkingDirectory=/opt/image-fetcher

## Generate Timelapse VideosEnvironmentFile=/opt/image-fetcher/config.env

ExecStart=/usr/bin/python3 /opt/image-fetcher/src/fetcher.py

Generate MP4 videos from images with filename overlay in the bottom-left corner.Restart=always

RestartSec=10

### From inside the container:

```bash[Install]

docker exec -it web bashWantedBy=multi-user.target

python src/timelapse.py /data/images -o /data/timelapse.mp4 --fps 30```

```

Reliability notes for a 2-year run:

### Options:- Use a bind-mounted persistent volume (e.g. external HDD or SSD) for `/data`.

```bash- Use Docker `--restart unless-stopped` or systemd `Restart=always` so crashes restart.

python src/timelapse.py /data/images \- Monitor disk usage; configure `MAX_FILES` or `MAX_AGE_DAYS` to limit storage.

  -o /data/timelapse.mp4 \- Consider rotating or syncing images offsite (rsync or rclone) periodically.

  --fps 30 \- Keep host updated; consider unattended-upgrades and power-fail measures.

  --start 20250101 \

  --end 20251231 \CI/CD:

  --no-overlay- The included GitHub Actions workflow builds the container and runs a quick import

```  test. To push images, add steps and registry secrets (GHCR, Docker Hub, etc.).



- **`--fps`** - frames per second (default: 30)Configuration environment variables (see `config.example.env`):

- **`--start YYYYMMDD`** - include images from this date onward- IMAGE_URL - required URL to fetch

- **`--end YYYYMMDD`** - include images up to this date- INTERVAL_SECONDS - seconds between fetches

- **`--no-overlay`** - disable filename text overlay- STORAGE_DIR - where images are stored (container: /data)

- MAX_FILES - max number of stored files (0 disabled)

### Download the video:- MAX_AGE_DAYS - max age in days (0 disabled)

```bash- TIMEOUT_SECONDS - HTTP timeout

docker cp web:/data/timelapse.mp4 ./timelapse.mp4- RETRY_COUNT - number of retries on error

```

# Debian server

## Configuration1. Download OS and copy image to Formated USB drive.

2. Boot server with USB drive and follow installation instructions.

All settings via environment variables in `docker-compose.yml`:3. Configure OS and updates:

 - accese as user

| Variable | Default | Description | - preventing shut down

|----------|---------|-------------| - update and upgrade

| `IMAGE_URL` | (required) | URL of image to fetch |4. install required packages:

| `INTERVAL_SECONDS` | 300 | Seconds between fetches | - docker

| `STORAGE_DIR` | `/data/images` | Where to store images | - python3

| `MAX_FILES` | 0 | Keep only N newest images (0 = unlimited) | - Git

| `MAX_AGE_DAYS` | 0 | Delete images older than N days (0 = unlimited) | - vs code

| `TIMEOUT_SECONDS` | 15 | HTTP request timeout | - unattended-upgrades

| `RETRY_COUNT` | 3 | Retry attempts on failure | - ssh

| `LOG_LEVEL` | INFO | Logging level (DEBUG, INFO, WARNING, ERROR) | - apache2

 - FFmpeg ( command in image dir for generating timelaps: ```ffmpeg -framerate 10 -pattern_type glob -i "*.JPG" -c:v libx264 -crf 20 -pix_fmt yuv420p output.mp4 ```)

Example custom configuration: - Gmerlin multimedia player (for viewing timelaps)

```yaml4. download, build and run image fetcher container as described above.

services:

  fetcher:When running the fetcher via docker compose the files are placed here:

    environment:```/var/lib/docker/volumes/byggeplasskamera_images/_data/images```
      - IMAGE_URL=https://kunde.byggekamera.no/?u=nytt-sykehus-aker&c=1059
      - INTERVAL_SECONDS=600
      - MAX_FILES=1000
      - MAX_AGE_DAYS=30
```

## File Storage

Images are stored in `./data/images/` on the host:

```
data/
  images/
    20250101_120000.jpg
    20250101_120300.jpg
    ...
    latest              ← symlink to newest image
    timelapse.mp4       ← (generated by timelapse.py)
```

## Long-Term Storage (2-Year Run)

### 1. Use an external drive
```bash
# Mount external drive to /mnt/storage
mkdir -p /mnt/storage
# In docker-compose.yml:
volumes:
  - /mnt/storage/camera:/data
```

### 2. Set retention policy
```yaml
environment:
  - MAX_FILES=2880     # ~24 hours at 30s interval
  # OR
  - MAX_AGE_DAYS=30    # keep last 30 days
```

### 3. Monitor disk usage
```bash
du -sh ./data/images/
```

### 4. Backup to remote location
```bash
# Add to crontab on Debian host
0 2 * * * rsync -av /path/to/data/images/ remote:/backup/camera/
```

### 5. Ensure auto-restart
- Docker: `--restart unless-stopped` (already in compose file)
- Systemd: `Restart=always` (see below)

## Systemd Alternative (Without Docker)

If you prefer native systemd instead of Docker:

1. Create virtualenv:
```bash
python3 -m venv /opt/image-fetcher/venv
source /opt/image-fetcher/venv/bin/activate
pip install -r requirements.txt
deactivate
```

2. Create `/etc/systemd/system/image-fetcher.service`:
```ini
[Unit]
Description=Image Fetcher
After=network-online.target

[Service]
Type=simple
User=fetcher
WorkingDirectory=/opt/image-fetcher
EnvironmentFile=/opt/image-fetcher/config.env
ExecStart=/opt/image-fetcher/venv/bin/python -u src/fetcher.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

3. Enable and start:
```bash
sudo systemctl daemon-reload
sudo systemctl enable image-fetcher
sudo systemctl start image-fetcher
```

## Debian Server Setup

### Installation Steps

1. Install Debian OS on your laptop
2. Install required packages:
```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y docker.io docker-compose git python3 ffmpeg curl
sudo usermod -aG docker $(whoami)
```

3. Configure unattended updates:
```bash
sudo apt install unattended-upgrades
sudo dpkg-reconfigure -plow unattended-upgrades
```

4. Clone repository:
```bash
git clone https://github.com/jyran1988/byggeplasskamera.git
cd byggeplasskamera
mkdir -p data
```

5. Start containers:
```bash
docker compose up -d --build
```

### Accessing the Server

From another machine on the network:
```bash
# View latest image
curl http://your-server-ip/latest > latest.jpg

# Download all images
wget -r http://your-server-ip/download/

# SSH for maintenance
ssh user@your-server-ip
```

## Troubleshooting

### No images appearing
```bash
docker compose logs fetcher
# Check URL is accessible: curl https://...
```

### Web server not responding
```bash
docker compose logs web
docker compose ps
```

### Out of disk space
```bash
du -sh ./data/images/*
# Enable retention: MAX_FILES=1000 or MAX_AGE_DAYS=30
```

### Timelapse video generation fails
```bash
docker exec -it web bash
python src/timelapse.py /data/images -o /tmp/test.mp4
# Check: ffmpeg, Pillow, disk space
```

## CI/CD

GitHub Actions workflow (`.github/workflows/ci.yml`):
- Installs dependencies
- Runs import test
- Builds Docker image

To push to a registry (GHCR/Docker Hub), add secrets and update workflow.

## File Structure

```
byggeplasskamera/
  src/
    fetcher.py          ← image downloader (runs continuously)
    web_server.py       ← Flask web server
    timelapse.py        ← video generator
  Dockerfile            ← container image definition
  docker-compose.yml    ← multi-service orchestration
  requirements.txt      ← Python dependencies
  README.md             ← this file
  .github/
    workflows/
      ci.yml            ← GitHub Actions pipeline
  data/                 ← images stored here (on host)
    images/
      (images and timelapse videos)
```

## License

See LICENSE file

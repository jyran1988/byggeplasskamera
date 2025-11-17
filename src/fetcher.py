#!/usr/bin/env python3
"""Lightweight image fetcher.

Fetches an image from a configurable URL on a configurable interval and stores
it to disk. Keeps a 'latest' symlink and supports retention by number of files
or max age (days).

Configuration via environment variables (see README and config.example.env).
"""
import os
import sys
import time
import logging
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import requests

# Defaults
IMAGE_URL = os.environ.get("IMAGE_URL")
INTERVAL_SECONDS = int(os.environ.get("INTERVAL_SECONDS", "3600"))  # 60 minutes
# Single-source storage dir (backwards compatible)
STORAGE_DIR = Path(os.environ.get("STORAGE_DIR", "/data/images"))
# Root where multiple sources live; each source will be stored under STORAGE_ROOT/<id>/images
STORAGE_ROOT = Path(os.environ.get("STORAGE_ROOT", str(STORAGE_DIR.parent)))
MAX_FILES = int(os.environ.get("MAX_FILES", "0"))  # 0 = disabled
MAX_AGE_DAYS = int(os.environ.get("MAX_AGE_DAYS", "0"))  # 0 = disabled
TIMEOUT_SECONDS = int(os.environ.get("TIMEOUT_SECONDS", "15"))
RETRY_COUNT = int(os.environ.get("RETRY_COUNT", "3"))
RETRY_BACKOFF_FACTOR = float(os.environ.get("RETRY_BACKOFF_FACTOR", "1.5"))

LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")

logging.basicConfig(stream=sys.stdout, level=LOG_LEVEL,
                    format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("fetcher")


def ensure_storage_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def slugify_id(s: str) -> str:
    # simple slug: allow alnum, dash, underscore; convert others to '_'
    out = []
    for ch in s:
        if ch.isalnum() or ch in ("-", "_"):
            out.append(ch)
        else:
            out.append("_")
    return "".join(out)


def parse_sources() -> list:
    """Parse SOURCES env var or fall back to IMAGE_URL.

    SOURCES format examples:
      "cam1=https://host/cam1.jpg,cam2=https://host/cam2.jpg"
      or semicolon separated.

    Returns list of dicts: {id, url, dir}
    """
    raw = os.environ.get("SOURCES")
    sources = []
    if raw:
        parts = [p.strip() for p in raw.replace(";", ",").split(",") if p.strip()]
        for p in parts:
            if "=" in p:
                sid, url = p.split("=", 1)
                sid = slugify_id(sid.strip()) or None
                url = url.strip()
            else:
                # If only URL provided, generate id from hostname
                url = p
                try:
                    sid = slugify_id(url.split("//")[-1].split("/")[0])
                except Exception:
                    sid = None
            if not sid:
                sid = f"camera_{len(sources)+1}"
            sources.append({"id": sid, "url": url})
    elif IMAGE_URL:
        sid = os.environ.get("SOURCE_ID") or STORAGE_DIR.name or "camera"
        sid = slugify_id(sid)
        sources.append({"id": sid, "url": IMAGE_URL})
    else:
        return []

    # Attach directory for each source
    for s in sources:
        sdir = STORAGE_ROOT / s["id"] / "images"
        s["dir"] = sdir
    return sources


def guess_extension(resp: requests.Response, url: str) -> str:
    # Try content-type first
    ct = resp.headers.get("content-type", "").split(";")[0].strip().lower()
    if ct in ("image/jpeg", "image/jpg"):
        return ".jpg"
    if ct == "image/png":
        return ".png"
    if ct == "image/gif":
        return ".gif"
    if ct == "image/webp":
        return ".webp"
    # Fallback to extension from url
    parsed_ext = Path(url.split("?")[0]).suffix
    if parsed_ext:
        return parsed_ext
    return ".img"


def filename_for_ts(ts: datetime, ext: str) -> str:
    return ts.strftime("%Y%m%d_%H%M%S") + ext


def save_image(content: bytes, path: Path) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "wb") as f:
        f.write(content)
    # atomic rename
    tmp.replace(path)


def rotate_storage(storage: Path, max_files: int = 0, max_age_days: int = 0) -> None:
    files = sorted([p for p in storage.iterdir() if p.is_file() and p.name != "latest"])
    # remove by count
    if max_files and len(files) > max_files:
        to_remove = files[: len(files) - max_files]
        for p in to_remove:
            try:
                p.unlink()
                logger.info("Removed old file (count): %s", p.name)
            except Exception:
                logger.exception("Failed to remove %s", p)
    # remove by age
    if max_age_days:
        cutoff = datetime.utcnow() - timedelta(days=max_age_days)
        for p in files:
            try:
                mtime = datetime.utcfromtimestamp(p.stat().st_mtime)
                if mtime < cutoff:
                    p.unlink()
                    logger.info("Removed old file (age): %s", p.name)
            except Exception:
                logger.exception("Failed to check/remove %s", p)


def try_fetch(url: str, timeout: int, retries: int, backoff: float) -> Optional[requests.Response]:
    attempt = 0
    while attempt <= retries:
        try:
            resp = requests.get(url, timeout=timeout)
            if resp.status_code == 200 and resp.content:
                return resp
            logger.warning("Non-200 status %s from %s", resp.status_code, url)
        except requests.RequestException:
            logger.exception("Request failed (attempt %d) for %s", attempt + 1, url)
        attempt += 1
        sleep = backoff ** attempt
        logger.debug("Sleeping %.1f seconds before retry", sleep)
        time.sleep(sleep)
    return None


def main() -> int:
    sources = parse_sources()
    if not sources:
        logger.error("No sources configured (set SOURCES or IMAGE_URL). Exiting.")
        return 2

    # ensure storage dirs exist
    for s in sources:
        ensure_storage_dir(s["dir"])

    logger.info("Starting image fetcher. sources=%s interval=%ds storage_root=%s", \
                ",".join([f"{s['id']}={s['url']}" for s in sources]), INTERVAL_SECONDS, STORAGE_ROOT)

    while True:
        start = time.time()
        # iterate through sources and fetch each once per cycle
        for s in sources:
            sid = s["id"]
            url = s["url"]
            sdir = s["dir"]
            try:
                resp = try_fetch(url, timeout=TIMEOUT_SECONDS, retries=RETRY_COUNT, backoff=RETRY_BACKOFF_FACTOR)
                if resp is not None:
                    ext = guess_extension(resp, url)
                    ts = datetime.utcnow()
                    fname = filename_for_ts(ts, ext)
                    dest = sdir / fname
                    save_image(resp.content, dest)
                    logger.info("[%s] Saved image: %s", sid, dest.name)
                    # update latest symlink
                    latest = sdir / "latest"
                    try:
                        if latest.exists() or latest.is_symlink():
                            latest.unlink()
                        latest.symlink_to(dest.name)
                    except Exception:
                        # If symlink not supported on FS, copy
                        try:
                            shutil.copy2(dest, sdir / "latest")
                        except Exception:
                            logger.exception("[%s] Failed to update latest link/file", sid)
                    # retention
                    rotate_storage(sdir, max_files=MAX_FILES, max_age_days=MAX_AGE_DAYS)
                else:
                    logger.warning("[%s] Failed to fetch image after retries", sid)
            except Exception:
                logger.exception("[%s] Failed processing source %s", sid, url)

        elapsed = time.time() - start
        sleep_for = INTERVAL_SECONDS - elapsed
        if sleep_for > 0:
            time.sleep(sleep_for)


if __name__ == "__main__":
    raise SystemExit(main())

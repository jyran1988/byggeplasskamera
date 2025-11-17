#!/usr/bin/env python3
"""Simple web server to serve latest image and list downloads."""
import os
import logging
from pathlib import Path
from flask import Flask, send_file, jsonify, redirect, url_for, request, render_template_string
import threading
import subprocess
import uuid
from datetime import datetime
import zipfile
import io

app = Flask(__name__)

STORAGE_DIR = Path(os.environ.get("STORAGE_DIR", "/data/images"))
# Root directory that may contain multiple camera folders, each with an images/ subdir
STORAGE_ROOT = Path(os.environ.get("STORAGE_ROOT", str(STORAGE_DIR.parent)))

LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")

logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("web_server")


def _discover_sources():
    """Return list of (id, dirpath) for discovered sources."""
    sources = []
    try:
        if STORAGE_ROOT.exists() and any(p.is_dir() for p in STORAGE_ROOT.iterdir()):
            for child in sorted([p for p in STORAGE_ROOT.iterdir() if p.is_dir()]):
                images_dir = child / "images"
                if images_dir.exists() and images_dir.is_dir():
                    dirpath = images_dir
                else:
                    dirpath = child
                sources.append((child.name, dirpath))
        else:
            sources.append((STORAGE_DIR.name or "camera", STORAGE_DIR))
    except Exception:
        sources.append((STORAGE_DIR.name or "camera", STORAGE_DIR))
    return sources


def _get_source_dir(source_id: str):
    """Map a source id to its directory Path or return None."""
    if not source_id:
        return STORAGE_DIR
    try:
        for sid, path in _discover_sources():
            if sid == source_id:
                return path
        # fallback: if source_id equals STORAGE_DIR.name
        if source_id == (STORAGE_DIR.name or "camera"):
            return STORAGE_DIR
    except Exception:
        return None
    return None


@app.route("/")
def index():
        """Render a multi-source UI: each discovered camera shows latest image, monthly thumbnails and latest timelapse."""

        # Discover sources under STORAGE_ROOT. If there are no subdirs, fall back to single STORAGE_DIR.
        sources = []
        try:
            if STORAGE_ROOT.exists() and any(p.is_dir() for p in STORAGE_ROOT.iterdir()):
                for child in sorted([p for p in STORAGE_ROOT.iterdir() if p.is_dir()]):
                    # If a subdir contains an images/ subfolder, prefer that.
                    images_dir = child / "images"
                    if images_dir.exists() and images_dir.is_dir():
                        dirpath = images_dir
                    else:
                        dirpath = child
                    sources.append({"id": child.name, "dir": dirpath})
            else:
                sources.append({"id": STORAGE_DIR.name or "camera", "dir": STORAGE_DIR})
        except Exception:
            sources = [{"id": STORAGE_DIR.name or "camera", "dir": STORAGE_DIR}]

        sources_data = []
        for src in sources:
            dirpath = src["dir"]
            imgs = []
            try:
                imgs = sorted([
                    p.name for p in dirpath.iterdir()
                    if p.is_file() and p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp") and p.name != "latest"
                ], reverse=True)
            except Exception:
                imgs = []

            monthly_images = {}
            for img in imgs:
                month_key = img[:6]
                if month_key not in monthly_images:
                    monthly_images[month_key] = img

            sorted_months = sorted(monthly_images.keys(), reverse=True)

            latest_img = None
            latest_link = None
            try:
                # prefer a 'latest' symlink if present
                latest_link_path = dirpath / "latest"
                if latest_link_path.exists() or latest_link_path.is_symlink():
                    latest_img = latest_link_path.name
                    latest_link = url_for("latest_source", source=src["id"])
                elif imgs:
                    latest_img = imgs[0]
                    latest_link = url_for("download_source", source=src["id"], filename=latest_img)
            except Exception:
                latest_img = None
                latest_link = None

            # find latest timelapse in this dir
            latest_timelapse = None
            try:
                timelapses = [ (p.stat().st_mtime, p.name) for p in dirpath.iterdir() if p.is_file() and p.suffix.lower() == ".mp4" ]
                timelapses.sort(reverse=True)
                if timelapses:
                    latest_timelapse = timelapses[0][1]
            except Exception:
                latest_timelapse = None

            sources_data.append({
                "id": src["id"],
                "dir": str(dirpath),
                "monthly_images": monthly_images,
                "sorted_months": sorted_months,
                "latest_link": latest_link,
                "latest_img": latest_img,
                "latest_timelapse": latest_timelapse,
            })

        html = """
        <!doctype html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width,initial-scale=1">
            <title>Libakkløkka - Multi Camera</title>
            <style>
                body { font-family: Arial, sans-serif; margin: 16px; }
                /* Layout: flexible columns that wrap on small screens */
                .sources { display:flex; gap:24px; align-items:flex-start; flex-wrap:wrap; }
                /* Each source column grows to fill available space but has a sensible min-width */
                .source { border:1px solid #ddd; padding:12px; border-radius:6px; flex:1 1 320px; box-sizing:border-box; max-width:48vw; }
                .source h2 { margin-top:0 }
                /* Make the latest image responsive and scale to column width */
                .source img { width:100%; height:auto; display:block; object-fit:contain; border:1px solid #ccc; }
                /* Thumbnails remain small but responsive */
                .month-thumb img { width:120px; max-width:30%; height:auto; border:1px solid #ccc; }
                /* Video should scale with the column */
                .source video { width:100%; height:auto; max-width:640px; display:block; }
                .meta { color:#666; font-size:0.9em }
            </style>
        </head>
        <body>
            <h1>Libakkløkka</h1>
            <div class="sources">
            {% for s in sources_data %}
                <div class="source">
                    <h2>Camera: {{ s.id }}</h2>
                    <div>
                        <h3>Latest</h3>
                        {% if s.latest_link %}
                            <a href="{{ s.latest_link }}"><img src="{{ s.latest_link }}?t={{ now_ts }}" alt="latest"></a>
                        {% else %}
                            <div class="meta">No latest image</div>
                        {% endif %}
                    </div>

                    <div>
                        <h3>Images by month</h3>
                        {% for month in s.sorted_months %}
                            {% set img = s.monthly_images[month] %}
                            <div class="month-thumb">
                                <a href="/source/{{ s.id }}/download/{{ img }}"><img src="/source/{{ s.id }}/download/{{ img }}" alt="{{ img }}" title="{{ img }}"></a>
                                <div class="meta"><a href="/source/{{ s.id }}/download/zip/{{ month }}">📦 Download all (zip)</a></div>
                            </div>
                        {% endfor %}
                    </div>

                    <div>
                        <h3>Latest timelapse</h3>
                        {% if s.latest_timelapse %}
                            <video controls width="420">
                                <source src="/source/{{ s.id }}/download/{{ s.latest_timelapse }}" type="video/mp4">
                                Your browser does not support the video tag.
                            </video>
                            <div class="meta">{{ s.latest_timelapse }}</div>
                        {% else %}
                            <div class="meta">No timelapse videos found yet.</div>
                        {% endif %}
                    </div>
                </div>
            {% endfor %}
            </div>

            <script>
                // auto-refresh every 30s
                setInterval(function(){
                    var imgs = document.querySelectorAll('img');
                    imgs.forEach(function(img){
                        var src = img.src.split('?')[0];
                        img.src = src + '?t=' + Date.now();
                    });
                }, 30000);
            </script>
        </body>
        </html>
        """

        return render_template_string(html, sources_data=sources_data, now_ts=int(datetime.utcnow().timestamp()))


@app.route("/latest")
def latest():
    """Serve the latest image."""
    latest_link = STORAGE_DIR / "latest"
    if latest_link.exists() or latest_link.is_symlink():
        try:
            return send_file(latest_link, mimetype="image/jpeg")
        except Exception as e:
            logger.exception("Failed to serve latest image")
            return jsonify({"error": str(e)}), 500
    return jsonify({"error": "No latest image available"}), 404


@app.route("/list")
def list_images():
    """List all images in JSON format."""
    try:
        files = sorted([
            p.name for p in STORAGE_DIR.iterdir()
            if p.is_file() and p.name != "latest"
        ], reverse=True)
        return jsonify({"images": files, "count": len(files)})
    except Exception as e:
        logger.exception("Failed to list images")
        return jsonify({"error": str(e)}), 500


@app.route("/download/<filename>")
def download(filename):
    """Download a specific image."""
    # sanitize filename to prevent path traversal
    if "/" in filename or "\\" in filename or filename.startswith("."):
        return jsonify({"error": "Invalid filename"}), 400
    
    file_path = STORAGE_DIR / filename
    if not file_path.exists():
        return jsonify({"error": "File not found"}), 404
    
    try:
        return send_file(file_path, as_attachment=True)
    except Exception as e:
        logger.exception("Failed to download %s", filename)
        return jsonify({"error": str(e)}), 500


@app.route("/source/<source>/latest")
def latest_source(source):
    """Serve the latest image for a specific source."""
    dirpath = _get_source_dir(source)
    if not dirpath:
        return jsonify({"error": "Source not found"}), 404

    latest_link = dirpath / "latest"
    if latest_link.exists() or latest_link.is_symlink():
        try:
            return send_file(latest_link)
        except Exception as e:
            logger.exception("Failed to serve latest image for %s", source)
            return jsonify({"error": str(e)}), 500

    # fallback: serve newest image file
    try:
        files = sorted([p for p in dirpath.iterdir() if p.is_file() and p.name != 'latest'], reverse=True)
        if files:
            return send_file(files[0])
    except Exception:
        pass
    return jsonify({"error": "No latest image available"}), 404


@app.route("/source/<source>/list")
def list_images_source(source):
    dirpath = _get_source_dir(source)
    if not dirpath:
        return jsonify({"error": "Source not found"}), 404
    try:
        files = sorted([p.name for p in dirpath.iterdir() if p.is_file() and p.name != 'latest'], reverse=True)
        return jsonify({"images": files, "count": len(files)})
    except Exception as e:
        logger.exception("Failed to list images for %s", source)
        return jsonify({"error": str(e)}), 500


@app.route("/source/<source>/download/<filename>")
def download_source(source, filename):
    # sanitize filename to prevent path traversal
    if "/" in filename or "\\" in filename or filename.startswith('.'):
        return jsonify({"error": "Invalid filename"}), 400
    dirpath = _get_source_dir(source)
    if not dirpath:
        return jsonify({"error": "Source not found"}), 404
    file_path = dirpath / filename
    if not file_path.exists():
        return jsonify({"error": "File not found"}), 404
    try:
        return send_file(file_path, as_attachment=True)
    except Exception as e:
        logger.exception("Failed to download %s from %s", filename, source)
        return jsonify({"error": str(e)}), 500


@app.route("/health")
def health():
    """Health check endpoint."""
    return jsonify({"status": "ok"})


# Simple in-memory job registry for async timelapse generation
jobs = {}


def _run_timelapse_subprocess(image_dir: str, output_path: str, fps: int, start: str, end: str, no_overlay: bool, job_id: str = None):
    args = ["python", "src/timelapse.py", image_dir, "-o", output_path, "--fps", str(fps)]
    if start:
        args += ["--start", start]
    if end:
        args += ["--end", end]
    if no_overlay:
        args += ["--no-overlay"]

    logger.info("Starting timelapse subprocess: %s", " ".join(args))
    start_ts = datetime.utcnow().isoformat() + "Z"
    if job_id:
        jobs[job_id].update({"status": "running", "started_at": start_ts})
    try:
        result = subprocess.run(args, capture_output=True, text=True)
        success = result.returncode == 0
        logger.info("Timelapse finished rc=%s stdout=%s stderr=%s", result.returncode, result.stdout[:200], result.stderr[:200])
        if job_id:
            jobs[job_id].update({
                "status": "finished" if success else "failed",
                "finished_at": datetime.utcnow().isoformat() + "Z",
                "exit_code": result.returncode,
                "output_path": output_path,
                "stderr": result.stderr[:200],
            })
    except Exception as e:
        logger.exception("Failed to run timelapse subprocess")
        if job_id:
            jobs[job_id].update({"status": "error", "error": str(e)})


@app.route("/timelapse", methods=["POST"])
def timelapse_trigger():
    """Trigger timelapse generation.

    Accepts form or JSON parameters:
    - fps (int)
    - start (YYYYMMDD)
    - end (YYYYMMDD)
    - no_overlay (bool)
    - async (bool) -> if true, returns job id and runs in background
    """
    data = request.get_json(silent=True) or request.form or request.args
    fps = int(data.get("fps", 30))
    start = data.get("start")
    end = data.get("end")
    no_overlay = str(data.get("no_overlay", "false")).lower() in ("1", "true", "yes")
    run_async = str(data.get("async", "false")).lower() in ("1", "true", "yes")

    source = data.get("source")
    source_dir = _get_source_dir(source) or STORAGE_DIR

    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    output_fname = f"timelapse_{timestamp}.mp4"
    output_path = str((source_dir / output_fname).resolve())

    # Ensure storage dir exists
    try:
        source_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        logger.exception("Failed to create storage dir %s", source_dir)
        return jsonify({"error": "Storage directory not available"}), 500

    if run_async:
        job_id = str(uuid.uuid4())
        jobs[job_id] = {
            "status": "queued",
            "created_at": datetime.utcnow().isoformat() + "Z",
            "output_path": output_path,
            "source": source,
        }
        thread = threading.Thread(target=_run_timelapse_subprocess, args=(str(source_dir), output_path, fps, start, end, no_overlay, job_id), daemon=True)
        thread.start()
        return jsonify({"job_id": job_id, "status": "queued", "output_path": output_path}), 202

    # Run synchronously
    try:
        _run_timelapse_subprocess(str(source_dir), output_path, fps, start, end, no_overlay)
        return jsonify({"status": "finished", "output_path": output_path}), 200
    except Exception as e:
        logger.exception("Synchronous timelapse failed")
        return jsonify({"error": str(e)}), 500


@app.route("/timelapse/<job_id>")
def timelapse_status(job_id):
    job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    return jsonify(job)


@app.route("/download/zip/<month>")
def download_zip(month):
    """Download all images from a specific month as a zip file.

    month format: YYYYMM (e.g., 202501)
    """
    if not month or len(month) != 6 or not month.isdigit():
        return jsonify({"error": "Invalid month format. Use YYYYMM"}), 400

    try:
        # Collect all files that start with this month
        files = [
            p for p in STORAGE_DIR.iterdir()
            if p.is_file() and p.name.startswith(month) and p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp")
        ]
        if not files:
            return jsonify({"error": "No images found for this month"}), 404

        # Create zip in memory
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for file_path in sorted(files):
                zf.write(file_path, arcname=file_path.name)

        zip_buffer.seek(0)
        return send_file(
            zip_buffer,
            mimetype="application/zip",
            as_attachment=True,
            download_name=f"images_{month}.zip"
        )
    except Exception as e:
        logger.exception("Failed to create zip for month %s", month)
        return jsonify({"error": str(e)}), 500


@app.route("/source/<source>/download/zip/<month>")
def download_zip_source(source, month):
    """Download all images for a month from a specific source as a zip."""
    if not month or len(month) != 6 or not month.isdigit():
        return jsonify({"error": "Invalid month format. Use YYYYMM"}), 400

    dirpath = _get_source_dir(source)
    if not dirpath:
        return jsonify({"error": "Source not found"}), 404

    try:
        files = [
            p for p in dirpath.iterdir()
            if p.is_file() and p.name.startswith(month) and p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp")
        ]
        if not files:
            return jsonify({"error": "No images found for this month"}), 404

        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for file_path in sorted(files):
                zf.write(file_path, arcname=file_path.name)

        zip_buffer.seek(0)
        return send_file(
            zip_buffer,
            mimetype="application/zip",
            as_attachment=True,
            download_name=f"images_{source}_{month}.zip"
        )
    except Exception as e:
        logger.exception("Failed to create zip for month %s on source %s", month, source)
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    logger.info("Starting web server. STORAGE_DIR=%s", STORAGE_DIR)
    app.run(host="0.0.0.0", port=5000, debug=False)

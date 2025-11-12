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
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")

logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("web_server")


@app.route("/")
def index():
        """Render a simple HTML UI: latest image, thumbnails grouped by month, and latest timelapse video."""
        try:
                all_images = sorted([
                        p.name for p in STORAGE_DIR.iterdir()
                        if p.is_file() and p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp") and p.name != "latest"
                ], reverse=True)
        except Exception:
                all_images = []

        # Group by month (YYYYMM), keep only latest per month
        monthly_images = {}
        for img in all_images:
            # Filename format: YYYYMMDD_HHMMSS.jpg
            month_key = img[:6]  # YYYYMM
            if month_key not in monthly_images:
                monthly_images[month_key] = img

        # Sort months descending (newest first)
        sorted_months = sorted(monthly_images.keys(), reverse=True)

        latest_url = url_for("latest")

        # find latest timelapse
        latest_timelapse = None
        try:
                timelapses = [ (p.stat().st_mtime, p.name) for p in STORAGE_DIR.iterdir() if p.is_file() and p.suffix.lower() == ".mp4" ]
                timelapses.sort(reverse=True)
                if timelapses:
                        latest_timelapse = timelapses[0][1]
        except Exception:
                latest_timelapse = None

        html = """
        <!doctype html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width,initial-scale=1">
            <title>Libakkløkka</title>
            <style>
                body { font-family: Arial, sans-serif; margin: 16px; }
                .row { display:flex; gap:16px; align-items:flex-start; }
                .monthly-group { margin-bottom:24px; }
                .monthly-group h3 { margin:8px 0; }
                .month-thumb { display:flex; align-items:center; gap:12px; }
                .month-thumb img { width:160px; height:auto; border:1px solid #ccc; }
                .month-thumb-info { display:flex; flex-direction:column; gap:8px; }
                .month-thumb-info a { padding:6px 12px; background:#007bff; color:#fff; text-decoration:none; border-radius:4px; font-size:0.9em; }
                .month-thumb-info a:hover { background:#0056b3; }
                .latest img { max-width:720px; height:auto; border:2px solid #333; }
                .video { margin-top:12px; }
                .meta { color:#666; font-size:0.9em }
            </style>
        </head>
        <body>
            <h1>Libakkløkka</h1>
            <div class="row">
                <div class="latest">
                    <h2>Latest image</h2>
                    <a href="{{ latest_url }}"><img id="latest-img" src="{{ latest_url }}" alt="latest"></a>
                    <div class="meta">Auto-refreshes every 30s</div>
                </div>
            </div>

            <div class="monthly-group">
                <h2>Images by month</h2>
                {% for month in sorted_months %}
                    {% set img = monthly_images[month] %}
                    <div class="monthly-group">
                        <h3>{{ month[:4] }}-{{ month[4:6] }}</h3>
                        <div class="month-thumb">
                            <a href="/download/{{ img }}"><img src="/download/{{ img }}" alt="{{ img }}" title="{{ img }}"></a>
                            <div class="month-thumb-info">
                                <a href="/download/zip/{{ month }}">📦 Download all (zip)</a>
                            </div>
                        </div>
                    </div>
                {% endfor %}
            </div>

            <div class="video">
                <h2>Latest timelapse</h2>
                {% if latest_timelapse %}
                    <video controls width="720">
                        <source src="/download/{{ latest_timelapse }}" type="video/mp4">
                        Your browser does not support the video tag.
                    </video>
                    <div class="meta">{{ latest_timelapse }}</div>
                {% else %}
                    <div class="meta">No timelapse videos found yet.</div>
                {% endif %}
            </div>

            <script>
                // auto-refresh latest image
                setInterval(function(){
                    var img = document.getElementById('latest-img');
                    if(!img) return;
                    var src = '{{ latest_url }}';
                    img.src = src + '?t=' + Date.now();
                }, 30000);
            </script>
        </body>
        </html>
        """

        return render_template_string(html, sorted_months=sorted_months, monthly_images=monthly_images, latest_url=latest_url, latest_timelapse=latest_timelapse)


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

    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    output_fname = f"timelapse_{timestamp}.mp4"
    output_path = str((STORAGE_DIR / output_fname).resolve())

    # Ensure storage dir exists
    try:
        STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    except Exception:
        logger.exception("Failed to create storage dir %s", STORAGE_DIR)
        return jsonify({"error": "Storage directory not available"}), 500

    if run_async:
        job_id = str(uuid.uuid4())
        jobs[job_id] = {
            "status": "queued",
            "created_at": datetime.utcnow().isoformat() + "Z",
            "output_path": output_path,
        }
        thread = threading.Thread(target=_run_timelapse_subprocess, args=(str(STORAGE_DIR), output_path, fps, start, end, no_overlay, job_id), daemon=True)
        thread.start()
        return jsonify({"job_id": job_id, "status": "queued", "output_path": output_path}), 202

    # Run synchronously
    try:
        _run_timelapse_subprocess(str(STORAGE_DIR), output_path, fps, start, end, no_overlay)
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


if __name__ == "__main__":
    logger.info("Starting web server. STORAGE_DIR=%s", STORAGE_DIR)
    app.run(host="0.0.0.0", port=5000, debug=False)

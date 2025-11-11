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

app = Flask(__name__)

STORAGE_DIR = Path(os.environ.get("STORAGE_DIR", "/data/images"))
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")

logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("web_server")


@app.route("/")
def index():
        """Render a simple HTML UI: latest image, thumbnails, and latest timelapse video."""
        try:
                images = sorted([
                        p.name for p in STORAGE_DIR.iterdir()
                        if p.is_file() and p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp") and p.name != "latest"
                ], reverse=True)
        except Exception:
                images = []

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
                .thumbs { display:flex; flex-wrap:wrap; gap:8px; max-width:100%; }
                .thumbs img { width:160px; height:auto; border:1px solid #ccc; }
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
                <div style="flex:1">
                    <h2>Recent images</h2>
                    <div class="thumbs">
                        {% for img in images %}
                            <a href="/download/{{ img }}"><img src="/download/{{ img }}" alt="{{ img }}" title="{{ img }}"></a>
                        {% endfor %}
                    </div>
                </div>
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

        return render_template_string(html, images=images, latest_url=latest_url, latest_timelapse=latest_timelapse)


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


if __name__ == "__main__":
    logger.info("Starting web server. STORAGE_DIR=%s", STORAGE_DIR)
    app.run(host="0.0.0.0", port=5000, debug=False)

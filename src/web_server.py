#!/usr/bin/env python3
"""Simple web server to serve latest image and list downloads."""
import os
import logging
from pathlib import Path
from flask import Flask, send_file, jsonify, redirect, url_for

app = Flask(__name__)

STORAGE_DIR = Path(os.environ.get("STORAGE_DIR", "/data/images"))
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")

logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("web_server")


@app.route("/")
def index():
    """Redirect to latest image or list files."""
    return redirect(url_for("latest"))


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


if __name__ == "__main__":
    logger.info("Starting web server. STORAGE_DIR=%s", STORAGE_DIR)
    app.run(host="0.0.0.0", port=5000, debug=False)

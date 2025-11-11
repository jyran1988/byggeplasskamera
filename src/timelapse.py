#!/usr/bin/env python3
"""Generate timelapse video from images with filename overlay."""
import os
import sys
import subprocess
import logging
import tempfile
from pathlib import Path
from datetime import datetime

# Requires: ffmpeg, PIL/Pillow

logging.basicConfig(level="INFO", format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("timelapse")


def generate_timelapse(
    image_dir: Path,
    output_path: Path,
    fps: int = 30,
    start_date: str = None,
    end_date: str = None,
    add_text_overlay: bool = True,
) -> bool:
    """
    Generate a timelapse video from images in a directory.
    
    Args:
        image_dir: directory containing images (YYYYMMDD_HHMMSS.jpg naming)
        output_path: path to write the output MP4
        fps: frames per second for the video
        start_date: filter images >= YYYYMMDD (optional)
        end_date: filter images <= YYYYMMDD (optional)
        add_text_overlay: add filename as text in bottom-left corner
    
    Returns:
        True if successful, False otherwise
    """
    image_dir = Path(image_dir)
    output_path = Path(output_path)
    
    if not image_dir.exists():
        logger.error("Image directory does not exist: %s", image_dir)
        return False
    
    # Get all image files, filter by date if provided
    images = sorted([
        p for p in image_dir.iterdir()
        if p.is_file() and p.suffix.lower() in (".jpg", ".jpeg", ".png", ".gif", ".webp")
    ])
    
    if start_date:
        images = [p for p in images if p.stem >= start_date]
    if end_date:
        images = [p for p in images if p.stem <= end_date]
    
    if not images:
        logger.error("No images found in %s (filtered)", image_dir)
        return False
    
    logger.info("Found %d images for timelapse", len(images))
    
    # If text overlay is requested, use ffmpeg with a text drawtext filter
    if add_text_overlay:
        return _generate_with_overlay(images, output_path, fps)
    else:
        return _generate_without_overlay(images, output_path, fps)


def _generate_without_overlay(images: list, output_path: Path, fps: int) -> bool:
    """Generate video without text overlay using concat demuxer."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        for img in images:
            duration = 1 / fps  # each image shown for 1 frame
            f.write(f"file '{img.absolute()}'\n")
            f.write(f"duration {duration}\n")
        concat_file = f.name
    
    try:
        cmd = [
            "ffmpeg",
            "-f", "concat",
            "-safe", "0",
            "-i", concat_file,
            "-vf", f"fps={fps}",
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-y",
            str(output_path),
        ]
        logger.info("Running: %s", " ".join(cmd))
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            logger.error("ffmpeg failed: %s", result.stderr)
            return False
        logger.info("Timelapse video created: %s", output_path)
        return True
    finally:
        Path(concat_file).unlink(missing_ok=True)


def _generate_with_overlay(images: list, output_path: Path, fps: int) -> bool:
    """Generate video with filename overlay in bottom-left corner."""
    # Use ffmpeg with a complex filter that draws the filename on each frame
    # We'll use the image sequence directly and apply text filter
    
    # Sort images and build input
    first_image = images[0]
    
    # Build a filtergraph with drawtext for each image
    # For simplicity, we'll use a single drawtext that references the input filename
    # FFmpeg's drawtext supports the metadata field 'lavfi.source.filename' but that's tricky
    # Alternative: use a script to generate labeled images, or use complex filter
    
    # Simpler approach: use imageclip in Python or just concat without overlay
    # For maximum compatibility, let's generate labeled images first
    
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        logger.error("PIL/Pillow not installed. Cannot add text overlay. Use: pip install Pillow")
        return _generate_without_overlay(images, output_path, fps)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        logger.info("Creating labeled images in temporary directory")
        
        # Copy/overlay text on each image
        for idx, img_path in enumerate(images):
            try:
                img = Image.open(img_path)
                # Ensure image is RGB for JPEG
                if img.mode != "RGB":
                    img = img.convert("RGB")
                draw = ImageDraw.Draw(img)
                
                # Try to load a font; fallback to default if not available
                try:
                    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 20)
                except (IOError, OSError):
                    font = ImageFont.load_default()
                
                # Draw filename in bottom-left corner with semi-transparent background
                text = img_path.name
                text_bbox = draw.textbbox((0, 0), text, font=font)
                text_width = text_bbox[2] - text_bbox[0]
                text_height = text_bbox[3] - text_bbox[1]
                
                margin = 10
                img_width, img_height = img.size
                x = margin
                y = img_height - text_height - margin
                
                # Semi-transparent black background for text
                bg_coords = [(x - 2, y - 2), (x + text_width + 2, y + text_height + 2)]
                draw.rectangle(bg_coords, fill=(0, 0, 0, 200))
                
                # Draw text
                draw.text((x, y), text, fill=(255, 255, 255, 255), font=font)
                
                # Save to temp directory
                # Save with a pure sequential numeric filename so ffmpeg can use %06d
                labeled_path = tmpdir / f"{idx:06d}.jpg"
                img.save(labeled_path, "JPEG")
                
                if (idx + 1) % 100 == 0:
                    logger.info("Labeled %d / %d images", idx + 1, len(images))
                    
            except Exception as e:
                logger.exception("Failed to label image %s", img_path)
                return False
        
        logger.info("All %d images labeled. Creating video...", len(images))

        # Use numeric sequence input (%06d.jpg)
        pattern = str(tmpdir / "%06d.jpg")
        cmd = [
            "ffmpeg",
            "-framerate", str(fps),
            "-i", pattern,
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-y",
            str(output_path),
        ]
        logger.info("Running: %s", " ".join(cmd))
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            logger.error("ffmpeg failed: %s", result.stderr)
            return False
        
        logger.info("Timelapse video created: %s", output_path)
        return True


def main() -> int:
    """CLI interface for generating timelapse."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Generate timelapse video from timestamped images"
    )
    parser.add_argument(
        "image_dir", help="Directory containing images (YYYYMMDD_HHMMSS.jpg format)"
    )
    parser.add_argument(
        "-o", "--output", default="timelapse.mp4", help="Output video file (default: timelapse.mp4)"
    )
    parser.add_argument(
        "--fps", type=int, default=30, help="Frames per second (default: 30)"
    )
    parser.add_argument(
        "--start", help="Start date filter (YYYYMMDD), inclusive"
    )
    parser.add_argument(
        "--end", help="End date filter (YYYYMMDD), inclusive"
    )
    parser.add_argument(
        "--no-overlay", action="store_true", help="Disable filename overlay"
    )
    
    args = parser.parse_args()
    
    success = generate_timelapse(
        image_dir=args.image_dir,
        output_path=args.output,
        fps=args.fps,
        start_date=args.start,
        end_date=args.end,
        add_text_overlay=not args.no_overlay,
    )
    
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())

"""
app.py
======
VB Image AI Studio - Flask server and public JSON API.

Run locally:
    python app.py      -> http://127.0.0.1:5000
"""

from __future__ import annotations

import logging
import os
import secrets
from typing import Any, Dict, Tuple

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request

import engine_router
import prompt_engine
import storage_manager

load_dotenv()

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("vb_image_studio")

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 64 * 1024  # JSON payloads only; images come from APIs.

MIN_DIMENSION = 256
MAX_DIMENSION = 1536


@app.after_request
def _security_headers(response):
    """Small hardening layer for a public-facing app."""
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    return response


@app.get("/")
def index():
    """Render the single-page studio UI."""
    return render_template("index.html")


@app.get("/api/health")
def health():
    """Lightweight health check for deployment monitoring."""
    return jsonify({"status": "ok", "service": "VB Image AI Studio", "version": "1.0"})


@app.get("/api/models")
def models():
    """Expose the model catalogue to the frontend."""
    return jsonify({"status": "success", "models": engine_router.supported_models()})


@app.post("/api/generate")
def generate():
    """
    Generate an image with the best available free engine.

    JSON body:
        prompt (str, required), model (str), width (int), height (int),
        seed (int), enhance (bool), style (str), batch is handled client-side,
        hf_token (str, optional).
    """
    payload: Dict[str, Any] = request.get_json(silent=True) or {}

    try:
        final_prompt, negative_prompt = prompt_engine.enhance_prompt(
            payload.get("prompt", ""),
            enhance=bool(payload.get("enhance", True)),
            style=str(payload.get("style", "none")),
        )
    except ValueError as exc:
        return jsonify({"status": "error", "error": str(exc)}), 400

    width, height, size_error = _validate_dimensions(payload)
    if size_error:
        return jsonify({"status": "error", "error": size_error}), 400

    seed, seed_error = _validate_seed(payload.get("seed"))
    if seed_error:
        return jsonify({"status": "error", "error": seed_error}), 400

    model = str(payload.get("model") or engine_router.DEFAULT_MODEL)
    token = str(payload.get("hf_token") or "").strip()

    try:
        result = engine_router.generate_image(
            prompt=final_prompt,
            model=model,
            width=width,
            height=height,
            seed=seed,
            negative_prompt=negative_prompt,
            hf_token=token,
        )
    except engine_router.GenerationError as exc:
        logger.error("Generation failed: %s", exc)
        return (
            jsonify({
                "status": "error",
                "error": "Image generation failed. Please try again or change the model.",
                "detail": str(exc)[:500],
            }),
            502,
        )

    try:
        entry = storage_manager.save_image(
            image_bytes=result["content"],
            prompt=final_prompt,
            model_used=result["model_used"],
            engine=result["engine"],
            width=width,
            height=height,
            seed=seed,
            extra={
                "original_prompt": str(payload.get("prompt", "")),
                "note": result.get("note", ""),
            },
        )
    except ValueError as exc:
        logger.error("Invalid image payload: %s", exc)
        return jsonify({"status": "error", "error": str(exc)}), 502
    except OSError as exc:
        logger.error("Could not save image: %s", exc)
        return jsonify({"status": "error", "error": "Could not save the generated image."}), 500

    return jsonify({
        "status": "success",
        "image_url": entry["image_url"],
        "filename": entry["filename"],
        "seed_used": seed,
        "prompt_used": final_prompt,
        "model_used": result["model_used"],
        "engine": result["engine"],
        "note": result.get("note", ""),
    })


@app.get("/api/gallery")
def gallery():
    """List previously generated images (newest first)."""
    try:
        limit = int(request.args.get("limit", 60))
    except (TypeError, ValueError):
        limit = 60
    return jsonify({"status": "success", "images": storage_manager.list_images(limit)})


@app.delete("/api/gallery/<path:filename>")
def delete_gallery_image(filename: str):
    """Delete one generated image from disk and history."""
    if not storage_manager.delete_image(filename):
        return jsonify({"status": "error", "error": "Image not found."}), 404
    return jsonify({"status": "success", "filename": filename})


@app.errorhandler(404)
def not_found(_error):
    return jsonify({"status": "error", "error": "Endpoint not found."}), 404


@app.errorhandler(500)
def internal_error(_error):
    logger.exception("Unhandled server error")
    return jsonify({"status": "error", "error": "Internal server error."}), 500


def _validate_dimensions(payload: Dict[str, Any]) -> Tuple[int, int, str]:
    """Validate and clamp width/height to a safe generation range."""
    try:
        width = int(payload.get("width", 1024))
        height = int(payload.get("height", 1024))
    except (TypeError, ValueError):
        return 0, 0, "Width and height must be integers."

    if not (MIN_DIMENSION <= width <= MAX_DIMENSION):
        return 0, 0, f"Width must be between {MIN_DIMENSION} and {MAX_DIMENSION}."
    if not (MIN_DIMENSION <= height <= MAX_DIMENSION):
        return 0, 0, f"Height must be between {MIN_DIMENSION} and {MAX_DIMENSION}."
    return width, height, ""


def _validate_seed(value: Any) -> Tuple[int, str]:
    """Accept an explicit seed or generate a random one."""
    if value in (None, "", 0, "0"):
        return secrets.randbelow(2 ** 31), ""
    try:
        seed = int(value)
    except (TypeError, ValueError):
        return 0, "Seed must be an integer."
    if not (0 <= seed < 2 ** 31):
        return 0, "Seed must be between 0 and 2147483647."
    return seed, ""


if __name__ == "__main__":
    storage_manager.ensure_dirs()
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    app.run(host="127.0.0.1", port=5000, debug=debug)

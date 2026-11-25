"""
engine_router.py
================
Sub-system 1: Multi-engine free API router with automatic failover.

Two free providers are supported:

* Pollinations AI  -> keyless, unlimited, used by default.
* Hugging Face     -> optional, activated with a free HF read token.

The router always returns raw image bytes plus metadata about the engine that
actually produced the image. Network errors, rate limits and model cold-starts
are retried before falling back to another free engine.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import re
import time
from typing import Any, Dict, Optional, Tuple
from urllib.parse import quote

import requests

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Model catalogue
# --------------------------------------------------------------------------- #

POLLINATIONS_MODELS = ("flux-realism", "flux", "any-dark", "turbo")
HF_MODELS = (
    "black-forest-labs/FLUX.1-schnell",
    "stabilityai/stable-diffusion-xl-base-1.0",
)

# Public model id -> (engine, provider model name, human readable label)
MODEL_ALIASES: Dict[str, Tuple[str, str, str]] = {
    "pollinations-flux-realism": ("pollinations", "flux-realism", "Pollinations Flux Realism"),
    "pollinations-flux": ("pollinations", "flux", "Pollinations Flux"),
    "pollinations-turbo": ("pollinations", "turbo", "Pollinations Turbo"),
    "pollinations-any-dark": ("pollinations", "any-dark", "Pollinations Any Dark"),
    "flux-realism": ("pollinations", "flux-realism", "Pollinations Flux Realism"),
    "flux": ("pollinations", "flux", "Pollinations Flux"),
    "turbo": ("pollinations", "turbo", "Pollinations Turbo"),
    "any-dark": ("pollinations", "any-dark", "Pollinations Any Dark"),
    "hf-flux": ("huggingface", "black-forest-labs/FLUX.1-schnell", "FLUX.1-schnell (HF)"),
    "hf-sdxl": ("huggingface", "stabilityai/stable-diffusion-xl-base-1.0", "SDXL 1.0 (HF)"),
    "flux-schnell": ("huggingface", "black-forest-labs/FLUX.1-schnell", "FLUX.1-schnell (HF)"),
    "sdxl": ("huggingface", "stabilityai/stable-diffusion-xl-base-1.0", "SDXL 1.0 (HF)"),
}

DEFAULT_MODEL = "pollinations-flux-realism"
REQUEST_TIMEOUT = (10, 120)  # (connect, read) in seconds
MAX_ATTEMPTS = 3


class GenerationError(RuntimeError):
    """Raised when every free engine failed to produce an image."""


class ProviderRateLimit(GenerationError):
    """Raised when a provider advertises a retry-after window."""

    def __init__(self, message: str, retry_after: int = 0):
        super().__init__(message)
        self.retry_after = retry_after


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def resolve_model(model: Optional[str]) -> Tuple[str, str, str]:
    """Resolve a UI model id to (engine, provider model, label)."""
    key = (model or DEFAULT_MODEL).strip().lower()
    if key in MODEL_ALIASES:
        return MODEL_ALIASES[key]

    # Accept raw provider model names as a convenience.
    if key in POLLINATIONS_MODELS:
        return ("pollinations", key, f"Pollinations {key.title()}")
    if key in HF_MODELS:
        return ("huggingface", key, key.split("/")[-1])

    return MODEL_ALIASES[DEFAULT_MODEL]


def supported_models() -> Dict[str, str]:
    """Return the model catalogue for API clients."""
    return {
        model_id: label
        for model_id, (_engine, _provider_model, label) in MODEL_ALIASES.items()
    }


def _looks_like_image(content: bytes, content_type: str) -> bool:
    """Cheap sanity check so JSON errors are never saved as images."""
    if content_type.startswith("image/"):
        return True
    return content[:8] in (b"\x89PNG\r\n\x1a\n", b"\xff\xd8\xff", b"GIF87a", b"GIF89a")


def _retry_after_seconds(response: requests.Response) -> int:
    """Read a provider-provided cooldown (header or JSON message)."""
    header = response.headers.get("Retry-After", "")
    if header.isdigit():
        return min(int(header), 60)
    try:
        payload = response.json()
        message = str(payload.get("error", {}).get("message", payload)) if isinstance(payload, dict) else str(payload)
        match = re.search(r"Retry after\s+(\d+)\s*s", message, re.IGNORECASE)
        if match:
            return min(int(match.group(1)) + 1, 60)
    except (ValueError, TypeError, AttributeError):
        pass
    return 5


def _hf_error_message(response: requests.Response) -> str:
    try:
        payload = response.json()
        if isinstance(payload, dict):
            return str(payload.get("error") or payload.get("message") or payload)[:300]
    except (ValueError, TypeError):
        pass
    return response.text[:300] or f"HTTP {response.status_code}"


# --------------------------------------------------------------------------- #
# Provider implementations
# --------------------------------------------------------------------------- #

def _generate_with_huggingface(
    prompt: str,
    provider_model: str,
    width: int,
    height: int,
    seed: int,
    negative_prompt: str,
    token: str,
) -> bytes:
    """Call the Hugging Face Inference API and return raw image bytes."""
    url = f"https://api-inference.huggingface.co/models/{provider_model}"
    parameters: Dict[str, Any] = {
        "width": width,
        "height": height,
        "num_inference_steps": 28,
        "guidance_scale": 7.5,
        "seed": seed,
    }
    if provider_model.endswith("FLUX.1-schnell"):
        parameters.pop("guidance_scale", None)
    if negative_prompt:
        parameters["negative_prompt"] = negative_prompt

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "User-Agent": "VB-Image-AI-Studio/1.0",
    }

    last_error = "unknown Hugging Face error"
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = requests.post(
                url, headers=headers, json={"inputs": prompt, "parameters": parameters},
                timeout=REQUEST_TIMEOUT,
            )
        except requests.RequestException as exc:
            last_error = f"network error: {exc}"
            logger.warning("HF attempt %s failed: %s", attempt, exc)
            time.sleep(2 ** (attempt - 1))
            continue

        content_type = response.headers.get("Content-Type", "")
        if response.status_code == 200 and _looks_like_image(response.content, content_type):
            return response.content

        last_error = _hf_error_message(response)
        if response.status_code == 200 and "json" in content_type:
            # Some inference endpoints return base64 encoded images.
            try:
                payload = response.json()
                if isinstance(payload, list) and payload and isinstance(payload[0], dict):
                    encoded = payload[0].get("generated_image")
                    if encoded:
                        return base64.b64decode(encoded)
            except (ValueError, TypeError, KeyError, base64.binascii.Error):
                pass

        if response.status_code in (429, 500, 502, 503, 504):
            wait = 3
            try:
                payload = response.json()
                if isinstance(payload, dict) and payload.get("estimated_time"):
                    wait = min(float(payload["estimated_time"]) + 1, 30)
            except (ValueError, TypeError):
                pass
            logger.info("HF retryable status %s, waiting %.1fs", response.status_code, wait)
            time.sleep(wait)
            continue

        break

    raise GenerationError(f"Hugging Face engine failed: {last_error}")


def _generate_with_pollinations(
    prompt: str,
    provider_model: str,
    width: int,
    height: int,
    seed: int,
    negative_prompt: str,
) -> bytes:
    """Call the keyless Pollinations image endpoint and return raw bytes."""
    encoded_prompt = quote(prompt, safe="")
    url = f"https://image.pollinations.ai/prompt/{encoded_prompt}"
    params: Dict[str, Any] = {
        "width": width,
        "height": height,
        "seed": seed,
        "model": provider_model,
        "nologo": "true",
        "enhance": "true",
    }
    if negative_prompt:
        params["negative"] = negative_prompt

    last_error = "unknown Pollinations error"
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = requests.get(
                url, params=params, headers={"User-Agent": "VB-Image-AI-Studio/1.0"},
                timeout=REQUEST_TIMEOUT,
            )
        except requests.RequestException as exc:
            last_error = f"network error: {exc}"
            logger.warning("Pollinations attempt %s failed: %s", attempt, exc)
            time.sleep(2 ** (attempt - 1))
            continue

        content_type = response.headers.get("Content-Type", "")
        if response.status_code == 200 and _looks_like_image(response.content, content_type):
            return response.content

        last_error = f"HTTP {response.status_code}: {response.text[:200]}"
        if response.status_code in (402, 429):
            # Free-tier cooldown is per IP, so switching models would not help.
            # Hand the advertised wait time to the router instead of retrying blindly.
            raise ProviderRateLimit(
                f"Pollinations engine failed: {last_error}",
                _retry_after_seconds(response),
            )
        if response.status_code in (500, 502, 503, 504):
            time.sleep(2 ** (attempt - 1))

    raise GenerationError(f"Pollinations engine failed: {last_error}")


# --------------------------------------------------------------------------- #
# Public router
# --------------------------------------------------------------------------- #

def generate_image(
    prompt: str,
    model: str = DEFAULT_MODEL,
    width: int = 1024,
    height: int = 1024,
    seed: int = 0,
    negative_prompt: str = "",
    hf_token: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Generate an image using the best available free engine.

    Returns a dict with ``content`` (raw bytes), ``engine``, ``model_used``,
    ``label`` and an optional ``note`` explaining any automatic fallback.
    """
    token = (hf_token or os.environ.get("HF_API_KEY") or "").strip()
    if token.lower() in ("your_huggingface_token_here", "none", "null"):
        token = ""

    engine, provider_model, label = resolve_model(model)
    note = ""

    if engine == "huggingface" and not token:
        note = "No Hugging Face token supplied - automatically used the keyless Pollinations engine."
        engine, provider_model, label = (
            "pollinations", "flux-realism", "Pollinations Flux Realism"
        )

    errors = []
    if engine == "huggingface":
        try:
            content = _generate_with_huggingface(
                prompt, provider_model, width, height, seed, negative_prompt, token
            )
            return {
                "content": content,
                "engine": "huggingface",
                "model_used": provider_model,
                "label": label,
                "note": note,
            }
        except GenerationError as exc:
            errors.append(str(exc))
            note = (note + " " if note else "") + "Hugging Face failed; used keyless fallback."
            logger.warning("HF engine failed, falling back: %s", exc)

    # Keyless path (also the universal fallback).
    providers = [provider_model] if engine == "pollinations" else []
    for fallback in POLLINATIONS_MODELS:
        if fallback not in providers:
            providers.append(fallback)

    rate_limit_retried = False
    for index, candidate in enumerate(providers):
        for attempt in (1, 2):
            try:
                content = _generate_with_pollinations(
                    prompt, candidate, width, height, seed, negative_prompt
                )
                label = MODEL_ALIASES.get(
                    f"pollinations-{candidate}", (None, None, f"Pollinations {candidate.title()}")
                )[2]
                if index > 0 or note:
                    note = (note + " " if note else "") + f"Switched to {label} to complete generation."
                return {
                    "content": content,
                    "engine": "pollinations",
                    "model_used": candidate,
                    "label": label,
                    "note": note,
                }
            except ProviderRateLimit as exc:
                errors.append(str(exc))
                if not rate_limit_retried and attempt == 1 and 0 < exc.retry_after <= 45:
                    rate_limit_retried = True
                    logger.info("Provider cooldown; waiting %ss before one retry", exc.retry_after)
                    time.sleep(exc.retry_after)
                    continue
                break
            except GenerationError as exc:
                errors.append(str(exc))
                break

    raise GenerationError("All free engines failed. " + " | ".join(errors[-3:]))

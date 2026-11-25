"""
prompt_engine.py
================
Sub-system 2: Prompt validation, realism enhancement and style presets.
"""

from __future__ import annotations

import re
from typing import Dict, Optional

MAX_PROMPT_LENGTH = 2000
DEFAULT_NEGATIVE_PROMPT = (
    "distorted, deformed, blurry, low quality, plastic texture, watermark, text, jpeg artifacts"
)

REALISM_TOKENS = (
    "photorealistic, ultra-detailed, 8k resolution, natural lighting, "
    "realistic textures, sharp focus, shot on 35mm lens"
)

STYLE_PRESETS: Dict[str, str] = {
    "none": "",
    "photorealistic": "photorealistic, natural lighting, realistic textures, 35mm lens",
    "cyberpunk": "cyberpunk, neon lights, futuristic city, moody atmosphere, high contrast",
    "anime": "anime style, clean line art, vibrant colors, detailed illustration",
    "3d-render": "3d render, octane render, ambient occlusion, soft shadows, depth of field",
    "cinematic": "cinematic still, dramatic lighting, anamorphic lens, film grain, depth of field",
    "oil-painting": "oil painting, visible brush strokes, canvas texture, classical composition",
}

_surprise_prompts = (
    "a quiet lighthouse at sunrise with waves crashing against the rocks",
    "a futuristic cyberpunk street market in the rain at night",
    "an astronaut sitting on a wooden chair in a vast lavender field",
    "a cozy bookshop interior with warm golden light and tall bookshelves",
    "a majestic snow leopard standing on a cliff in the Himalayas",
    "a vintage sports car parked in front of a neon motel at dusk",
    "a floating crystal island above a sea of clouds at golden hour",
    "a small village surrounded by cherry blossom trees in spring",
    "a portrait of an elderly fisherman with weathered hands and kind eyes",
    "a robotic gardener tending to glowing flowers in a glass greenhouse",
)


def sanitize_prompt(prompt: str) -> str:
    """Strip control characters and enforce a safe prompt length."""
    if not isinstance(prompt, str):
        raise ValueError("Prompt must be a string.")
    cleaned = "".join(ch for ch in prompt if ch in "\n\t" or ord(ch) >= 32).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    if not cleaned:
        raise ValueError("Prompt cannot be empty.")
    if len(cleaned) > MAX_PROMPT_LENGTH:
        raise ValueError(f"Prompt is too long (maximum {MAX_PROMPT_LENGTH} characters).")
    return cleaned


def enhance_prompt(
    prompt: str,
    enhance: bool = True,
    style: Optional[str] = None,
    negative_prompt: str = DEFAULT_NEGATIVE_PROMPT,
) -> tuple[str, str]:
    """
    Build the final prompt.

    Returns ``(final_prompt, negative_prompt)``. The negative prompt is only
    forwarded to engines that support it.
    """
    cleaned = sanitize_prompt(prompt)
    parts = [cleaned]

    style_key = (style or "none").strip().lower()
    style_tokens = STYLE_PRESETS.get(style_key, "")
    if style_tokens and style_tokens.lower() not in cleaned.lower():
        parts.append(style_tokens)

    if enhance and REALISM_TOKENS.lower() not in cleaned.lower():
        parts.append(REALISM_TOKENS)

    return ", ".join(parts), (negative_prompt or "").strip()


def random_prompt() -> str:
    """Return a ready-made creative prompt for the 'Surprise Me' button."""
    import random

    return random.choice(_surprise_prompts)


def style_presets() -> Dict[str, str]:
    """Return the available style presets (id -> description)."""
    return dict(STYLE_PRESETS)

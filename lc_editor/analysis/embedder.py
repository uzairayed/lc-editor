"""Optional CLIP / BLIP relevance for adaptive understand (Train B).

Never required. Soft-imports only. Does not download weights; returns None when
torch / transformers / open_clip are missing or models are unavailable offline.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from functools import lru_cache
from typing import Any

from lc_editor.analysis.manifest import Shot

EmbedderFn = Callable[[Shot, str], float | None]


def vision_extra_enabled() -> bool:
    """Opt-in via env so agents never pull multi-GB weights by accident."""
    raw = (os.environ.get("LC_EDITOR_VISION") or "").strip().lower()
    return raw in {"1", "true", "yes", "on", "clip", "blip"}


def _try_import_torch() -> Any | None:
    try:
        import torch  # type: ignore

        return torch
    except Exception:
        return None


@lru_cache(maxsize=1)
def _clip_bundle() -> tuple[Any, Any, Any] | None:
    """Return (model, preprocess, tokenizer) or None. No network download forced."""
    if not vision_extra_enabled():
        return None
    torch = _try_import_torch()
    if torch is None:
        return None
    # Prefer open_clip when present; fall back to transformers CLIPModel.
    try:
        import open_clip  # type: ignore

        model, _, preprocess = open_clip.create_model_and_transforms(
            "ViT-B-32",
            pretrained="openai",
        )
        tokenizer = open_clip.get_tokenizer("ViT-B-32")
        model.eval()
        return model, preprocess, tokenizer
    except Exception:
        pass
    try:
        from transformers import CLIPModel, CLIPProcessor  # type: ignore

        # local_files_only avoids silent Hub downloads when offline.
        model = CLIPModel.from_pretrained("openai/clip-vit-base-patch32", local_files_only=True)
        processor = CLIPProcessor.from_pretrained(
            "openai/clip-vit-base-patch32", local_files_only=True
        )
        model.eval()
        return model, processor, "transformers-clip"
    except Exception:
        return None


@lru_cache(maxsize=1)
def _blip_bundle() -> tuple[Any, Any] | None:
    if not vision_extra_enabled():
        return None
    torch = _try_import_torch()
    if torch is None:
        return None
    try:
        from transformers import BlipForImageTextRetrieval, BlipProcessor  # type: ignore

        processor = BlipProcessor.from_pretrained(
            "Salesforce/blip-itm-base-coco", local_files_only=True
        )
        model = BlipForImageTextRetrieval.from_pretrained(
            "Salesforce/blip-itm-base-coco", local_files_only=True
        )
        model.eval()
        return model, processor
    except Exception:
        return None


def clip_available() -> bool:
    return _clip_bundle() is not None


def blip_available() -> bool:
    return _blip_bundle() is not None


def score_clip(shot: Shot, query: str) -> float | None:
    bundle = _clip_bundle()
    if bundle is None or not query.strip():
        return None
    torch = _try_import_torch()
    if torch is None:
        return None
    path = shot.keyframe
    if not path:
        return None
    try:
        from PIL import Image
    except Exception:
        return None
    try:
        image = Image.open(path).convert("RGB")
    except Exception:
        return None

    model, preprocess_or_processor, tokenizer = bundle
    try:
        with torch.no_grad():
            if tokenizer == "transformers-clip":
                processor = preprocess_or_processor
                inputs = processor(text=[query], images=image, return_tensors="pt", padding=True)
                out = model(**inputs)
                # logits_per_image: similarity
                val = float(out.logits_per_image[0][0].item())
                # Map loosely into [0, 1] via sigmoid.
                return 1.0 / (1.0 + math_exp(-val / 5.0))
            # open_clip path
            import open_clip  # type: ignore

            image_t = preprocess_or_processor(image).unsqueeze(0)
            text_t = tokenizer([query])
            image_f = model.encode_image(image_t)
            text_f = model.encode_text(text_t)
            image_f = image_f / image_f.norm(dim=-1, keepdim=True)
            text_f = text_f / text_f.norm(dim=-1, keepdim=True)
            sim = float((image_f @ text_f.T)[0, 0].item())
            return max(0.0, min(1.0, (sim + 1.0) / 2.0))
    except Exception:
        return None


def math_exp(x: float) -> float:
    import math

    return math.exp(max(-50.0, min(50.0, x)))


def score_blip(shot: Shot, query: str) -> float | None:
    bundle = _blip_bundle()
    if bundle is None or not query.strip():
        return None
    torch = _try_import_torch()
    if torch is None:
        return None
    path = shot.keyframe
    if not path:
        return None
    try:
        from PIL import Image
    except Exception:
        return None
    try:
        image = Image.open(path).convert("RGB")
    except Exception:
        return None
    model, processor = bundle
    try:
        with torch.no_grad():
            inputs = processor(images=image, text=query, return_tensors="pt")
            out = model(**inputs, use_itm_head=True)
            # ITM head: softmax over match/no-match when available.
            logits = getattr(out, "itm_score", None)
            if logits is None:
                logits = getattr(out, "logits", None)
            if logits is None:
                return None
            probs = torch.softmax(logits, dim=-1)
            # Index 1 is typically "match".
            if probs.shape[-1] >= 2:
                return float(probs[0, 1].item())
            return float(probs.flatten()[0].item())
    except Exception:
        return None


def optional_embedder() -> EmbedderFn | None:
    """Best available optional scorer, or None (heuristic-only path)."""
    if not vision_extra_enabled():
        return None
    if clip_available():

        def _clip(shot: Shot, query: str) -> float | None:
            return score_clip(shot, query)

        return _clip
    if blip_available():

        def _blip(shot: Shot, query: str) -> float | None:
            return score_blip(shot, query)

        return _blip
    return None


def embedder_status() -> dict:
    return {
        "enabled": vision_extra_enabled(),
        "clip": clip_available(),
        "blip": blip_available(),
        "active": optional_embedder() is not None,
    }


__all__ = [
    "blip_available",
    "clip_available",
    "embedder_status",
    "optional_embedder",
    "score_blip",
    "score_clip",
    "vision_extra_enabled",
]

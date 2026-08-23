from __future__ import annotations

from typing import Any

from lc_editor.models import LEGAL_EFFECTS, EffectInstance
from lc_editor.ops.timeline import Reject
from lc_editor.render.paths import ffmpeg_path

EFFECT_SPEC: dict[str, dict[str, Any]] = {
    "blur": {"params": {"amount": (0.0, 8.0, 2.0)}, "kinds": {"video", "image", "clip"}},
    "sharpen": {"params": {"amount": (0.0, 2.0, 0.8)}, "kinds": {"video", "image", "clip"}},
    "glow": {"params": {"amount": (0.0, 1.0, 0.35)}, "kinds": {"video", "image", "clip"}},
    "grain": {"params": {"amount": (0.0, 1.0, 0.2)}, "kinds": {"video", "image", "clip", "text"}},
    "vignette": {"params": {"amount": (0.0, 1.0, 0.25)}, "kinds": {"video", "image", "clip"}},
    "lut": {"params": {"intensity": (0.0, 1.0, 1.0), "cube": ""}, "kinds": {"video", "image", "clip"}},
    "color": {
        "params": {"contrast": (0.5, 2.0, 1.0), "saturation": (0.0, 2.0, 1.0), "brightness": (-0.3, 0.3, 0.0)},
        "kinds": {"video", "image", "clip"},
    },
}


def validate_effect(name: str, params: dict | None, kind: str = "clip") -> dict[str, float | str]:
    if name not in LEGAL_EFFECTS or name not in EFFECT_SPEC:
        raise Reject(f"SPEC-RND-16: unknown effect {name}")
    spec = EFFECT_SPEC[name]
    if kind not in spec["kinds"]:
        raise Reject(f"SPEC-RND-16: {name} is not valid on {kind}")
    incoming = dict(params or {})
    if any(key in incoming for key in ("filter", "vf", "filter_complex")):
        raise Reject("SPEC-RND-16: raw filter strings are rejected")
    out: dict[str, float | str] = {}
    for key, bounds in spec["params"].items():
        if isinstance(bounds, tuple):
            lo, hi, default = bounds
            raw = incoming.get(key, default)
            try:
                value = float(raw)
            except (TypeError, ValueError) as exc:
                raise Reject(f"SPEC-RND-16: {name}.{key} must be a number") from exc
            if value < lo or value > hi:
                raise Reject(f"SPEC-RND-16: {name}.{key} must be {lo}-{hi}")
            out[key] = value
        else:
            out[key] = str(incoming.get(key, bounds) or "")
    return out


def compile_effect(effect: EffectInstance) -> str:
    if not effect.enabled:
        return ""
    name = effect.name
    params = effect.params
    if name == "blur":
        amount = max(0.1, float(params.get("amount", 2.0)))
        return f"boxblur={amount:.2f}:1"
    if name == "sharpen":
        amount = float(params.get("amount", 0.8))
        return f"unsharp=5:5:{amount:.2f}:5:5:0.0"
    if name == "glow":
        amount = float(params.get("amount", 0.35))
        return f"gblur=sigma={1 + amount * 4:.2f},eq=brightness={amount * 0.08:.3f}"
    if name == "grain":
        strength = max(1, int(round(float(params.get("amount", 0.2)) * 4)))
        return f"noise=alls={strength}:allf=t+u"
    if name == "vignette":
        amount = float(params.get("amount", 0.25))
        return f"vignette=angle=PI/5*{amount:.3f}:mode=forward"
    if name == "lut":
        cube = str(params.get("cube") or "")
        mix = float(params.get("intensity", 1.0))
        if not cube:
            return ""
        lut = f"lut3d=file='{ffmpeg_path(cube)}'"
        return lut if mix >= 0.999 else f"{lut},hue=s={mix:.3f}"
    if name == "color":
        contrast = float(params.get("contrast", 1.0))
        sat = float(params.get("saturation", 1.0))
        bright = float(params.get("brightness", 0.0))
        return f"eq=contrast={contrast:.3f}:saturation={sat:.3f}:brightness={bright:.3f}"
    return ""


def compile_effects(effects: list[EffectInstance]) -> str:
    parts = [compile_effect(e) for e in effects]
    return ",".join(p for p in parts if p)

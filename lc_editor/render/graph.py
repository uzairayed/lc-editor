from __future__ import annotations

from pathlib import Path

from lc_editor.models import CANVAS_H, CANVAS_W, FPS, AdjustmentLayer, Caption, Clip, MediaItem, Project
from lc_editor.render.captions import drawtext_filter, fontfile_for
from lc_editor.render.motion import crop_9_16, motion_chain
from lc_editor.render.paths import ffmpeg_path
from lc_editor.render.transitions import close_fade_filter, flash_filter, match_filter, punch_in_filter, whip_filter

EQ_KEYS = frozenset({"contrast", "brightness", "saturation", "gamma", "gamma_r", "gamma_g", "gamma_b", "r", "g", "b"})
COLORBALANCE_KEYS = frozenset({"rs", "gs", "bs", "rm", "gm", "bm", "rh", "gh", "bh"})


def preview_video_filters(clip: Clip, media: MediaItem) -> str:
    from lc_editor.models import PROXY_H, PROXY_W

    return (
        f"scale={PROXY_W}:{PROXY_H}:force_original_aspect_ratio=increase,"
        f"crop={PROXY_W}:{PROXY_H}"
    )


def clip_video_filters(
    clip: Clip,
    media: MediaItem,
    captions: list[Caption],
    project: Project,
    *,
    last: bool = False,
    transition: str | None = None,
    preview: bool = False,
    composed: bool = False,
) -> str:
    if preview:
        return preview_video_filters(clip, media)
    frames = max(1, int(round(clip.duration_s * FPS)))
    parts: list[str] = []
    if not composed:
        parts.append(crop_9_16(clip, media.width or CANVAS_W, media.height or CANVAS_H))
    if clip.motion != "none":
        parts.append(motion_chain(clip, frames))
    elif composed:
        parts.append(f"scale={CANVAS_W}:{CANVAS_H}")
    for cap in captions:
        if cap.textfile:
            parts.append(drawtext_filter(cap, Path(cap.textfile), fontfile_for(cap)))
    if last and project.overlays.end_card:
        parts.append("drawtext=textfile='endcard.txt':expansion=none:fontsize=48:x=(w-text_w)/2:y=h*0.8")
    if clip.speed != 1.0:
        parts.append(f"setpts=PTS/{clip.speed}")
    if clip.wrap == "soft":
        parts.append("unsharp=5:5:0.8:5:5:0.0")
    if transition == "close_fade" and last:
        parts.append(close_fade_filter(frames))
    if transition == "flash":
        parts.append(flash_filter())
    if transition == "match":
        parts.append(match_filter())
    if transition == "punch":
        parts.append(punch_in_filter())
    return ",".join(parts)


def hero_encode_args(output: Path) -> list[str]:
    # CRF 18 + tune grain: temporal grain noise boils into wavy macroblocks
    # at x264 defaults, especially across the two-pass intermediate+concat encode.
    return [
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "18",
        "-tune",
        "grain",
        "-pix_fmt",
        "yuv420p",
        "-r",
        str(FPS),
        "-s",
        f"{CANVAS_W}x{CANVAS_H}",
        "-c:a",
        "aac",
        "-movflags",
        "+faststart",
        str(output),
    ]


def proxy_encode_args(output: Path) -> list[str]:
    from lc_editor.models import PROXY_H, PROXY_W

    return [
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "30",
        "-pix_fmt",
        "yuv420p",
        "-s",
        f"{PROXY_W}x{PROXY_H}",
        "-c:a",
        "aac",
        "-movflags",
        "+faststart",
        str(output),
    ]


def concat_list(paths: list[Path], list_path: Path) -> Path:
    lines = [f"file '{p.resolve().as_posix()}'" for p in paths]
    list_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return list_path


def clip_hash_payload(clip: Clip, captions: list[Caption], project: Project, *, preview: bool = False) -> dict:
    payload = {
        "media_id": clip.media_id,
        "in_s": clip.in_s,
        "out_s": clip.out_s,
        "duration_s": clip.duration_s,
        "motion": clip.motion,
        "focus": [clip.focus_x, clip.focus_y],
        "speed": clip.speed,
        "wrap": clip.wrap,
        "kenburns_amount": clip.kenburns_amount,
        "zoom_frames": clip.zoom_frames,
        "zoom_amount": clip.zoom_amount,
        "effects": [e.model_dump() for e in clip.effects],
        "layout": clip.layout,
        "panes": [pane.model_dump() for pane in clip.panes],
        "captions": [(c.text, c.y_pct, c.role, c.enter) for c in captions if c.clip_id == clip.id],
        "preview": preview,
    }
    return payload


def resolved_adjustment(project: Project) -> AdjustmentLayer:
    layer = project.adjustment
    if not layer.enabled:
        return layer
    return layer.model_copy(
        update={
            "grade_preset": layer.grade_preset or project.grade_preset,
            "cube_path": layer.cube_path or project.cube_path,
            "grain": layer.grain if layer.grain > 0 else project.grain,
            "vignette": layer.vignette if layer.vignette > 0 else project.vignette,
        }
    )


def _colon_filter(name: str, params: dict[str, float], allowed: frozenset[str]) -> str:
    bits = [f"{key}={params[key]}" for key in sorted(params) if key in allowed]
    return f"{name}={':'.join(bits)}" if bits else ""


def adjustment_filters(project: Project, *, duration_s: float = 0.0) -> str:
    layer = resolved_adjustment(project)
    if not layer.enabled:
        return ""
    parts: list[str] = []
    if layer.eq or layer.colorbalance:
        if layer.eq:
            eq = _colon_filter("eq", layer.eq, EQ_KEYS)
            if eq:
                parts.append(eq)
        if layer.colorbalance:
            cb = _colon_filter("colorbalance", layer.colorbalance, COLORBALANCE_KEYS)
            if cb:
                parts.append(cb)
    else:
        cube = layer.cube_path
        if cube:
            mix = layer.intensity
            lut = f"lut3d=file='{ffmpeg_path(cube)}'"
            if mix >= 0.999:
                parts.append(lut)
            else:
                parts.append(f"{lut},hue=s={mix}")
    # Sharpen before adding grain so unsharp does not amplify per-frame noise flicker.
    if layer.wrap == "soft":
        parts.append("unsharp=5:5:0.8:5:5:0.0")
    if layer.grain > 0:
        strength = max(1, int(round(layer.grain * 4)))
        parts.append(f"noise=alls={strength}:allf=t+u")
    if layer.vignette > 0:
        parts.append(f"vignette=angle=PI/5*{layer.vignette}:mode=forward")
    if layer.fade and duration_s > 0:
        frames = max(1, int(round(duration_s * FPS)))
        parts.append(close_fade_filter(frames))
    if layer.end_hold_s > 0:
        parts.append(f"tpad=stop_mode=clone:stop_duration={layer.end_hold_s}")
    return ",".join(parts)


def whip_graph() -> str:
    return whip_filter()


def punch_graph() -> str:
    return punch_in_filter()


def close_fade_graph(total_frames: int) -> str:
    return close_fade_filter(total_frames)

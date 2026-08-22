from __future__ import annotations

from pathlib import Path

from lc_editor.models import CANVAS_H, CANVAS_W, FPS, Caption, Clip, MediaItem, Project
from lc_editor.render.captions import drawtext_filter, fontfile_for
from lc_editor.render.motion import crop_9_16, motion_chain
from lc_editor.render.paths import ffmpeg_path
from lc_editor.render.transitions import close_fade_filter, flash_filter, match_filter, punch_in_filter, whip_filter


def clip_video_filters(
    clip: Clip,
    media: MediaItem,
    captions: list[Caption],
    project: Project,
    *,
    last: bool = False,
    transition: str | None = None,
) -> str:
    frames = max(1, int(round(clip.duration_s * FPS)))
    parts = [crop_9_16(clip, media.width or CANVAS_W, media.height or CANVAS_H)]
    if clip.motion != "none":
        parts.append(motion_chain(clip, frames))
    cube = project.cube_path
    if cube:
        mix = clip.grade_intensity
        lut = f"lut3d=file='{ffmpeg_path(cube)}'"
        if mix >= 0.999:
            parts.append(lut)
        else:
            parts.append(f"{lut},hue=s={mix}")
    for cap in captions:
        if cap.textfile:
            parts.append(drawtext_filter(cap, Path(cap.textfile), fontfile_for(cap)))
    if last and project.overlays.end_card:
        parts.append("drawtext=textfile='endcard.txt':expansion=none:fontsize=48:x=(w-text_w)/2:y=h*0.8")
    if clip.speed != 1.0:
        parts.append(f"setpts=PTS/{clip.speed}")
    if clip.wrap == "soft":
        parts.append("unsharp=5:5:0.8:5:5:0.0")
    if project.grain > 0:
        strength = max(1, int(round(project.grain * 8)))
        parts.append(f"noise=alls={strength}:allf=t")
    if project.vignette > 0:
        parts.append(f"vignette=angle=PI/5*{project.vignette}:mode=forward")
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
    return [
        "-c:v",
        "libx264",
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


def clip_hash_payload(clip: Clip, captions: list[Caption], project: Project) -> dict:
    return {
        "media_id": clip.media_id,
        "in_s": clip.in_s,
        "out_s": clip.out_s,
        "duration_s": clip.duration_s,
        "motion": clip.motion,
        "focus": [clip.focus_x, clip.focus_y],
        "grade": [project.grade_preset, clip.grade_intensity, clip.protect],
        "speed": clip.speed,
        "wrap": clip.wrap,
        "kenburns_amount": clip.kenburns_amount,
        "look": [project.grain, project.vignette],
        "captions": [(c.text, c.y_pct, c.role, c.enter) for c in captions if c.clip_id == clip.id],
    }


def whip_graph() -> str:
    return whip_filter()


def punch_graph() -> str:
    return punch_in_filter()


def close_fade_graph(total_frames: int) -> str:
    return close_fade_filter(total_frames)

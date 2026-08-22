from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

ASPECT_9_16 = "9:16"
CANVAS_W = 1080
CANVAS_H = 1920
FPS = 30
DURATION_CAP_S = 45.0
DURATION_SOFT_MAX_S = 28.0
DURATION_SOFT_MIN_S = 15.0
LOCKED_STILL_MAX_S = 1.4
DEFAULT_CLIP_S = 2.0
DEFAULT_STILL_S = 2.5
CAPTION_WRAP = 26
CAPTION_MAX_WORDS = 10
CAPTION_MAX_LINES = 2
CAPTION_Y_MIN = 0.22
CAPTION_Y_MAX = 0.50
CAPTION_Y_DEFAULT = 0.36
SFX_UNDER_BED_DB = 6.0
HIGHPASS_DEFAULT_HZ = 100.0
PROXY_W = 540
PROXY_H = 960
PUNCH_FRAMES = 4
WHIP_FRAMES = 8
CLOSE_FADE_FRAMES = 4
KENBURNS_ZOOM = 1.06
PUNCH_ZOOM = 1.08
SAND = "0xF6EBD4"
STROKE = "0x1A1410"
STROKE_W = 3

MotionKind = Literal["none", "kenburns", "punch"]
TransitionKind = Literal["hard", "whip", "punch", "close_fade"]
CaptionRole = Literal["title", "body"]
BedKind = Literal["wind", "room", "none"]
GradePreset = Literal["motovlog", "winter_trip", "neutral"]
SfxKind = Literal[
    "tick",
    "pop",
    "whoosh",
    "impact",
    "riser",
    "wind",
    "room",
    "steps_snow",
    "steps_gravel",
    "engine",
]
MEDIA_VIDEO_EXT = {".mp4", ".mov", ".m4v", ".mkv", ".webm", ".avi"}
MEDIA_IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff"}
MUSIC_KINDS = {"music", "melody", "drum", "drum_loop", "score", "cinematic", "ambient_music"}


class Clip(BaseModel):
    id: str
    media_id: str
    in_s: float = 0.0
    out_s: float = DEFAULT_CLIP_S
    duration_s: float = DEFAULT_CLIP_S
    start_s: float = 0.0
    motion: MotionKind = "none"
    focus_x: float = 0.5
    focus_y: float = 0.5
    gain_db: float = 0.0
    muted: bool = False
    grade_intensity: float = 1.0
    protect: bool = False
    is_still: bool = False


class Caption(BaseModel):
    id: str
    clip_id: str
    text: str
    role: CaptionRole = "body"
    y_pct: float = CAPTION_Y_DEFAULT
    lines: list[str] = Field(default_factory=list)
    hold_s: float = 1.5
    textfile: str = ""


class SfxPlacement(BaseModel):
    id: str
    kind: str
    at_s: float
    gain_db: float = -12.0
    auto: bool = False
    key: str = ""


class OverlayFlags(BaseModel):
    social_chrome: bool = False
    series_card: bool = False
    location_chip: bool = False
    progress: bool = False
    end_card: bool = False
    preview_guides: bool = False
    preview_platform: str = ""


class Timeline(BaseModel):
    clips: list[Clip] = Field(default_factory=list)
    captions: list[Caption] = Field(default_factory=list)
    sfx: list[SfxPlacement] = Field(default_factory=list)
    transitions: dict[str, TransitionKind] = Field(default_factory=dict)
    bed_kind: BedKind = "none"
    bed_gain_db: float = -6.0
    duck: bool = False
    highpass_hz: float | None = None
    version: int = 0


class MediaItem(BaseModel):
    id: str
    path: str
    original_path: str
    kind: Literal["video", "image"] = "video"
    duration_s: float = 0.0
    width: int = 0
    height: int = 0
    fps: float = FPS
    has_audio: bool = False
    burst_cover: bool = False
    burst_id: str = ""


class Project(BaseModel):
    id: str
    name: str
    aspect: str = ASPECT_9_16
    width: int = CANVAS_W
    height: int = CANVAS_H
    fps: int = FPS
    allow_music: bool = False
    grade_preset: GradePreset = "neutral"
    cube_path: str | None = None
    overlays: OverlayFlags = Field(default_factory=OverlayFlags)
    reviewed_version: int | None = None
    preset: str | None = None
    root: str = ""


class TimelineSummary(BaseModel):
    version: int
    clip_count: int
    duration_s: float
    caption_count: int
    transition_count: int


def timeline_duration(timeline: Timeline) -> float:
    return round(sum(c.duration_s for c in timeline.clips), 4)


def recompute_starts(timeline: Timeline) -> Timeline:
    t = 0.0
    clips: list[Clip] = []
    for clip in timeline.clips:
        clips.append(clip.model_copy(update={"start_s": round(t, 4)}))
        t += clip.duration_s
    return timeline.model_copy(update={"clips": clips})


def decorated_transition_count(timeline: Timeline) -> int:
    return sum(1 for kind in timeline.transitions.values() if kind not in ("hard",))


def summary_of(timeline: Timeline) -> TimelineSummary:
    decorated = decorated_transition_count(timeline)
    return TimelineSummary(
        version=timeline.version,
        clip_count=len(timeline.clips),
        duration_s=timeline_duration(timeline),
        caption_count=len(timeline.captions),
        transition_count=decorated,
    )


def envelope(ok: bool, timeline: Timeline, warnings: list[str]) -> dict:
    return {
        "ok": ok,
        "timeline_summary": summary_of(timeline).model_dump(),
        "warnings": list(warnings),
    }

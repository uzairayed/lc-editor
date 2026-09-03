from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

ASPECT_9_16 = "9:16"
CANVAS_W = 1080
CANVAS_H = 1920
FPS = 30
DURATION_CAP_S = 60.0
DURATION_SOFT_MAX_S = 28.0
DURATION_SOFT_MIN_S = 15.0
LOCKED_STILL_MAX_S = 1.4
DEFAULT_CLIP_S = 2.0
DEFAULT_STILL_S = 2.5
SHOT_MIN_S = 0.5
SHOT_MAX_S = 8.0
SHOT_ACK_MIN_S = 2.4
STILL_ACK_MIN_S = 2.2
MAX_CLIPS_PER_60S = 16
CAPTION_WRAP = 26
CAPTION_MAX_WORDS = 16
CAPTION_MAX_LINES = 3
CAPTION_LINE_MAX = 28
CAPTION_HOLD_CAP_S = 5.0
CAPTION_Y_MIN = 0.22
CAPTION_Y_MAX = 0.50
CAPTION_Y_DEFAULT = 0.36
CAPTION_SAFE_X0 = 64
CAPTION_SAFE_X1 = 853
CAPTION_SAFE_Y0 = 270
CAPTION_SAFE_Y1 = 1248
CAPTION_BAND_Y0 = 422
CAPTION_BAND_Y1 = 960
CAPTION_BOXW = 789
CAPTION_SIZE_MIN = 52
CAPTION_PROTECT_PX = 80
PHONE_PROOF_W = 270
PHONE_PROOF_H = 480
CaptionEnter = Literal["none", "fade", "punch"]
CaptionStyle = Literal["phrase", "karaoke", "pop"]
WordEmphasis = Literal["pop", "enlarge", "scream"]
KARAOKE_FILL = "0xFFE14A"
POP_FILL = "0xFFE14A"
TextMotion = Literal["none", "fade", "pop", "slide", "type_on"]
LayerKind = Literal["video", "image", "text"]
LayoutKind = Literal["stack_v", "stack_h", "stack_v3", "grid_2x2"]
EaseKind = Literal["linear", "smoothstep"]
EffectName = Literal["blur", "sharpen", "glow", "grain", "vignette", "lut", "color"]
BeatSubdivision = Literal["1", "1/2", "1/4"]
SCHEMA_V1 = 1
SCHEMA_V2 = 2
SFX_UNDER_BED_DB = 6.0
HIGHPASS_DEFAULT_HZ = 120.0
TRUE_PEAK_LIMIT_DBTP = -1.0
AUDIO_XFADE_MS_DEFAULT = 10.0
JL_CUT_FRAMES = 10
SPEED_MIN = 0.85
SPEED_MAX = 1.15
PROXY_W = 540
PROXY_H = 960
SOURCE_PROXY_W = 360
SOURCE_PROXY_H = 640
PUNCH_FRAMES = 4
WHIP_FRAMES = 8
CLOSE_FADE_FRAMES = 4
KENBURNS_ZOOM = 1.06
PUNCH_ZOOM = 1.08
ZOOM_HIT_FRAMES = 27
ZOOM_HIT_AMOUNT = 1.10
ZOOM_HIT_MIN_FRAMES = 18
ZOOM_HIT_MAX_FRAMES = 42
ZOOM_HIT_MIN_AMOUNT = 1.06
ZOOM_HIT_MAX_AMOUNT = 1.14
ZOOM_PAIR_MIN_HOLD_S = 0.40
ZOOM_PAIR_MIN_CLIP_S = 3.5
ZOOM_SUGGEST_SKIP_S = 2.5
SAND = "0xF6EBD4"
STROKE = "0x1A1410"
STROKE_W = 3

MotionKind = Literal["none", "kenburns", "punch", "zoom_in", "zoom_out", "zoom_pair"]
TransitionKind = Literal["hard", "whip", "punch", "close_fade", "j_cut", "l_cut", "flash", "match"]
DenoiseProfile = Literal["off", "outdoor", "indoor", "auto"]
LEGAL_TRANSITIONS = ("hard", "whip", "punch", "close_fade", "j_cut", "l_cut", "flash", "match")
DECORATED_TRANSITIONS = ("whip", "punch", "close_fade", "j_cut", "l_cut", "flash", "match")
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
    "sparkle",
    "swipe",
    "bubble",
    "button",
    "paper",
    "cash",
    "click",
    "correct",
    "success",
]
MEDIA_VIDEO_EXT = {".mp4", ".mov", ".m4v", ".mkv", ".webm", ".avi"}
MEDIA_IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff"}
MEDIA_AUDIO_EXT = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".aiff"}
MUSIC_KINDS = {"music", "melody", "drum", "drum_loop", "score", "cinematic", "ambient_music"}
LEGAL_EFFECTS = ("blur", "sharpen", "glow", "grain", "vignette", "lut", "color")
LEGAL_LAYOUTS = ("stack_v", "stack_h", "stack_v3", "grid_2x2")
LAYOUT_PANE_COUNT = {"stack_v": 2, "stack_h": 2, "stack_v3": 3, "grid_2x2": 4}
BEAT_CONFIDENCE_WARN = 0.45
MUSIC_HOT_DB = -3.0


class Transform(BaseModel):
    x: float = 0.5
    y: float = 0.5
    scale: float = 1.0
    rotation: float = 0.0
    opacity: float = 1.0


class Keyframe(BaseModel):
    t_s: float
    x: float | None = None
    y: float | None = None
    scale: float | None = None
    rotation: float | None = None
    opacity: float | None = None
    ease: EaseKind = "smoothstep"


class EffectInstance(BaseModel):
    id: str
    name: str
    params: dict[str, float | str | bool] = Field(default_factory=dict)
    enabled: bool = True


class TextStyle(BaseModel):
    role: CaptionRole = "body"
    fill: str = SAND
    stroke: str = STROKE
    stroke_w: int = STROKE_W
    motion: TextMotion = "fade"


class LayerItem(BaseModel):
    id: str
    kind: LayerKind
    z: int = 10
    start_s: float = 0.0
    duration_s: float = 2.0
    media_id: str | None = None
    in_s: float = 0.0
    text: str = ""
    role: CaptionRole = "body"
    clip_id: str | None = None
    caption_id: str | None = None
    y_pct: float = CAPTION_Y_DEFAULT
    lines: list[str] = Field(default_factory=list)
    hold_s: float = 1.5
    textfile: str = ""
    style: TextStyle = Field(default_factory=TextStyle)
    transform: Transform = Field(default_factory=Transform)
    keyframes: list[Keyframe] = Field(default_factory=list)
    effects: list[EffectInstance] = Field(default_factory=list)


class MusicTrack(BaseModel):
    id: str
    media_id: str
    start_s: float = 0.0
    in_s: float = 0.0
    duration_s: float = 0.0
    gain_db: float = -8.0
    fade_in_s: float = 0.4
    fade_out_s: float = 0.8
    loop: bool = False
    duck_natural: bool = True
    source_name: str = ""
    license_note: str = ""


class BeatGrid(BaseModel):
    media_id: str
    bpm: float = 120.0
    offset_s: float = 0.0
    beats: list[float] = Field(default_factory=list)
    downbeats: list[float] = Field(default_factory=list)
    sections: list[dict] = Field(default_factory=list)
    confidence: float = 0.0
    source: Literal["auto", "manual"] = "auto"


class LayoutPane(BaseModel):
    media_id: str
    in_s: float = 0.0
    focus_x: float = 0.5
    focus_y: float = 0.5


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
    denoise: DenoiseProfile = "auto"
    gate: bool = True
    speed: float = 1.0
    wrap: Literal["off", "soft"] = "off"
    kenburns_amount: float = KENBURNS_ZOOM
    zoom_frames: int = ZOOM_HIT_FRAMES
    zoom_amount: float = ZOOM_HIT_AMOUNT
    zoom_frames_out: int = ZOOM_HIT_FRAMES
    zoom_at_s: float | None = None
    effects: list[EffectInstance] = Field(default_factory=list)
    layout: LayoutKind | None = None
    panes: list[LayoutPane] = Field(default_factory=list)


def is_layout_clip(clip: Clip) -> bool:
    return bool(clip.layout and clip.panes)


def clip_media_ids(clip: Clip) -> list[str]:
    if is_layout_clip(clip):
        return [pane.media_id for pane in clip.panes]
    return [clip.media_id]


class CaptionWord(BaseModel):
    id: str = ""
    text: str
    start_s: float
    end_s: float
    emphasis: WordEmphasis = "pop"


class Caption(BaseModel):
    id: str
    clip_id: str
    text: str
    role: CaptionRole = "body"
    y_pct: float = CAPTION_Y_DEFAULT
    lines: list[str] = Field(default_factory=list)
    hold_s: float = 1.5
    textfile: str = ""
    enter: CaptionEnter = "fade"
    style: CaptionStyle = "phrase"
    words: list[CaptionWord] = Field(default_factory=list)


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


class AdjustmentLayer(BaseModel):
    enabled: bool = True
    grade_preset: GradePreset | None = None
    cube_path: str | None = None
    intensity: float = 1.0
    grain: float = 0.0
    vignette: float = 0.0
    wrap: Literal["off", "soft"] = "off"
    eq: dict[str, float] | None = None
    colorbalance: dict[str, float] | None = None
    fade: bool = False
    end_hold_s: float = 0.0


class Timeline(BaseModel):
    schema_version: int = SCHEMA_V2
    clips: list[Clip] = Field(default_factory=list)
    captions: list[Caption] = Field(default_factory=list)
    layers: list[LayerItem] = Field(default_factory=list)
    sfx: list[SfxPlacement] = Field(default_factory=list)
    music: list[MusicTrack] = Field(default_factory=list)
    beat_grid: BeatGrid | None = None
    template_id: str | None = None
    transitions: dict[str, TransitionKind] = Field(default_factory=dict)
    bed_kind: BedKind = "none"
    bed_gain_db: float = -6.0
    duck: bool = False
    highpass_hz: float | None = None
    audio_xfade_ms: float = AUDIO_XFADE_MS_DEFAULT
    version: int = 0


class MediaItem(BaseModel):
    id: str
    path: str
    original_path: str
    kind: Literal["video", "image", "audio"] = "video"
    duration_s: float = 0.0
    width: int = 0
    height: int = 0
    fps: float = FPS
    has_audio: bool = False
    burst_cover: bool = False
    burst_id: str = ""
    proxy_path: str = ""


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
    grain: float = 0.0
    vignette: float = 0.0
    adjustment: AdjustmentLayer = Field(default_factory=AdjustmentLayer)
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
    return sum(1 for kind in timeline.transitions.values() if kind in DECORATED_TRANSITIONS)


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

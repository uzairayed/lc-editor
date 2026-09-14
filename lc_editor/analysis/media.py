from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from lc_editor.models import FPS, MEDIA_AUDIO_EXT, MEDIA_IMAGE_EXT, MEDIA_VIDEO_EXT, SOURCE_SHORT_MIN

PXL_BURST = re.compile(r"^(PXL_.+?)[\._-]BURST", re.IGNORECASE)
_EXIF_DT = re.compile(r"^(\d{4}):(\d{2}):(\d{2})[ T](\d{2}):(\d{2}):(\d{2})")


def probe_args(ffprobe: str, path: Path) -> list[str]:
    return [
        ffprobe,
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(path),
    ]


def short_side(width: int, height: int) -> int:
    if width <= 0 or height <= 0:
        return 0
    return min(width, height)


def is_sub_720(width: int, height: int) -> bool:
    side = short_side(width, height)
    return 0 < side < SOURCE_SHORT_MIN


def resolution_label(width: int, height: int) -> str:
    if width <= 0 or height <= 0:
        return ""
    return f"{width}x{height}"


def resolution_boost(width: int, height: int) -> float:
    side = short_side(width, height)
    if side >= 1080:
        return 0.10
    if side >= SOURCE_SHORT_MIN:
        return 0.05
    return 0.0


def public_media(item, *, index: dict | None = None) -> dict:
    data = item.model_dump() if hasattr(item, "model_dump") else dict(item)
    width = int(data.get("width") or 0)
    height = int(data.get("height") or 0)
    data["resolution"] = resolution_label(width, height)
    data["sub_720"] = is_sub_720(width, height)
    if index:
        data.update(index)
    return data


def media_index_summary(shots: list) -> dict:
    """Cheap per-media rollup from a shot manifest for media_list filters."""
    if not shots:
        return {
            "motion": None,
            "blur": None,
            "audio_class": None,
            "keyframe": None,
            "shot_count": 0,
        }
    motions = [float(s.metrics.motion) for s in shots]
    blurs = [float(s.metrics.blur) for s in shots]
    classes = [s.metrics.audio_class for s in shots]
    # Prefer the sharpest (least blurry) keyframe as the cover thumb.
    cover = min(shots, key=lambda s: (s.metrics.blur, s.id))
    dominant = max(set(classes), key=classes.count)
    return {
        "motion": round(max(motions), 4),
        "blur": round(min(blurs), 4),
        "audio_class": dominant,
        "keyframe": cover.keyframe,
        "shot_count": len(shots),
    }


def quality_import_warning(item) -> str | None:
    data = item.model_dump() if hasattr(item, "model_dump") else dict(item)
    if data.get("kind") == "audio":
        return None
    width = int(data.get("width") or 0)
    height = int(data.get("height") or 0)
    if not is_sub_720(width, height):
        return None
    who = f"media {data['id']}" if data.get("id") else "source"
    return (
        f"SPEC-QLT-01: {who} is {resolution_label(width, height)} "
        f"(short side below {SOURCE_SHORT_MIN}); soft source"
    )


def quality_soft_warnings(items) -> list[str]:
    out: list[str] = []
    for item in items:
        warning = quality_import_warning(item)
        if warning:
            out.append(warning)
    return out


def parse_probe(payload: str, fallback_kind: str) -> dict:
    data = json.loads(payload)
    streams = data.get("streams") or []
    video = next((s for s in streams if s.get("codec_type") == "video"), {})
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    fmt = data.get("format") or {}
    fps = FPS
    rate = video.get("avg_frame_rate") or video.get("r_frame_rate") or "30/1"
    if isinstance(rate, str) and "/" in rate:
        num, den = rate.split("/", 1)
        if float(den) != 0:
            fps = float(num) / float(den)
    duration = float(fmt.get("duration") or 0.0)
    kind = fallback_kind
    if fallback_kind == "audio" or (not video and audio):
        kind = "audio"
    return {
        "width": int(video.get("width") or 0),
        "height": int(video.get("height") or 0),
        "duration_s": duration,
        "fps": fps,
        "has_audio": audio is not None or kind == "audio",
        "kind": kind,
        "color_space": str(video.get("color_space") or ""),
        "color_transfer": str(video.get("color_transfer") or ""),
        "color_primaries": str(video.get("color_primaries") or ""),
        "field_order": str(video.get("field_order") or ""),
        "creation_time": creation_time_from_probe(data),
    }


def _tag_creation_time(blob: dict | None) -> str | None:
    tags = (blob or {}).get("tags") or {}
    for key, val in tags.items():
        if str(key).lower() == "creation_time" and val:
            return str(val)
    return None


def creation_time_from_probe(data: dict | None) -> str | None:
    if not data:
        return None
    raw = data.get("creation_time")
    if raw:
        return str(raw)
    found = _tag_creation_time(data.get("format") if isinstance(data.get("format"), dict) else data)
    if found:
        return found
    for stream in data.get("streams") or []:
        if isinstance(stream, dict):
            found = _tag_creation_time(stream)
            if found:
                return found
    return None


def normalize_captured_at(raw: str | None) -> str | None:
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    match = _EXIF_DT.match(text)
    if match:
        text = (
            f"{match.group(1)}-{match.group(2)}-{match.group(3)}"
            f"T{match.group(4)}:{match.group(5)}:{match.group(6)}"
        )
    elif " " in text and "T" not in text[:20]:
        text = text.replace(" ", "T", 1)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        return parsed.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return parsed.strftime("%Y-%m-%dT%H:%M:%S")


def parse_captured_at(value: str | None) -> datetime | None:
    iso = normalize_captured_at(value)
    if not iso:
        return None
    text = iso[:-1] + "+00:00" if iso.endswith("Z") else iso
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def captured_at_sort_key(value: str | None, index: int = 0) -> tuple:
    parsed = parse_captured_at(value)
    if parsed is None:
        return (1, 0.0, index)
    stamp = parsed.timestamp() if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc).timestamp()
    return (0, stamp, index)


def mtime_iso(path: Path) -> str | None:
    try:
        stamp = path.stat().st_mtime
    except OSError:
        return None
    return datetime.fromtimestamp(stamp, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def read_exif_tags(path: Path) -> dict[str, str]:
    try:
        from PIL import Image
        from PIL.ExifTags import Base, IFD
    except ImportError:
        return {}
    try:
        with Image.open(path) as image:
            exif = image.getexif()
            if not exif:
                return {}
            out: dict[str, str] = {}
            dated = exif.get(Base.DateTime) or exif.get(306)
            if dated:
                out["DateTime"] = str(dated)
            try:
                ifd = exif.get_ifd(IFD.Exif)
            except Exception:
                ifd = {}
            original = (ifd or {}).get(Base.DateTimeOriginal) or (ifd or {}).get(36867)
            if original:
                out["DateTimeOriginal"] = str(original)
            return out
    except Exception:
        return {}


def _exif_original(exif: dict | None) -> str | None:
    for key, val in (exif or {}).items():
        if str(key).lower().replace("_", "") == "datetimeoriginal":
            return None if val is None else str(val)
    return None


def resolve_captured_at(
    *,
    probe: dict | None = None,
    exif: dict | None = None,
    path: Path | None = None,
) -> tuple[str | None, str | None]:
    iso = normalize_captured_at(creation_time_from_probe(probe))
    if iso:
        return iso, "probe"
    iso = normalize_captured_at(_exif_original(exif))
    if iso:
        return iso, "exif"
    if path is not None:
        iso = mtime_iso(path)
        if iso:
            return iso, "mtime"
    return None, None


def normalize_shoot_day(value: int | str | None) -> int | str | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    text = str(value).strip()
    if not text:
        return None
    if text.isdigit() or (text[0] == "-" and text[1:].isdigit()):
        return int(text)
    return text


def shoot_days_equal(left: int | str | None, right: int | str | None) -> bool:
    a = normalize_shoot_day(left)
    b = normalize_shoot_day(right)
    if a is None or b is None:
        return False
    return a == b or str(a).lower() == str(b).lower()


def normalize_role(value: str | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def roles_equal(left: str | None, right: str | None) -> bool:
    a = normalize_role(left)
    b = normalize_role(right)
    if a is None or b is None:
        return False
    return a.lower() == b.lower()


def kind_for(path: Path) -> str | None:
    ext = path.suffix.lower()
    if ext in MEDIA_VIDEO_EXT:
        return "video"
    if ext in MEDIA_IMAGE_EXT:
        return "image"
    if ext in MEDIA_AUDIO_EXT:
        return "audio"
    return None


def burst_groups(paths: list[Path]) -> dict[str, list[Path]]:
    groups: dict[str, list[Path]] = defaultdict(list)
    pat = re.compile(r"^(.*?)(\d+)$")
    for path in paths:
        stem = path.stem
        m = pat.match(stem)
        if m:
            groups[m.group(1)].append(path)
        else:
            groups[stem].append(path)
    return {k: sorted(v) for k, v in groups.items() if len(v) >= 3}


def pxl_burst_id(path: Path) -> str | None:
    match = PXL_BURST.match(path.name)
    if match:
        return match.group(1)
    return None


def select_import_paths(paths: list[Path]) -> tuple[list[Path], list[Path], list[str]]:
    bursts: dict[str, list[Path]] = defaultdict(list)
    others: list[Path] = []
    for path in paths:
        burst_id = pxl_burst_id(path)
        if burst_id:
            bursts[burst_id].append(path)
        else:
            others.append(path)
    kept: list[Path] = []
    skipped: list[Path] = []
    for burst_id, members in bursts.items():
        cover = next((m for m in members if "COVER" in m.name.upper()), None)
        if cover is None:
            cover = sorted(members)[0]
        kept.append(cover)
        skipped.extend(m for m in members if m != cover)
    return sorted(kept + others), skipped, sorted(bursts.keys())


def mark_burst_covers(items: list[dict]) -> None:
    by_burst: dict[str, list[dict]] = defaultdict(list)
    for item in items:
        if item.get("burst_id"):
            by_burst[item["burst_id"]].append(item)
    for group in by_burst.values():
        if not group:
            continue
        cover = next((item for item in group if item.get("burst_cover")), group[0])
        for item in group:
            item["burst_cover"] = item is cover or item.get("original_path", "").upper().find("COVER") >= 0
        if not any(item.get("burst_cover") for item in group):
            group[0]["burst_cover"] = True

from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path

from lc_editor.models import FPS, MEDIA_IMAGE_EXT, MEDIA_VIDEO_EXT

PXL_BURST = re.compile(r"^(PXL_.+?)[\._-]BURST", re.IGNORECASE)


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
    return {
        "width": int(video.get("width") or 0),
        "height": int(video.get("height") or 0),
        "duration_s": duration,
        "fps": fps,
        "has_audio": audio is not None,
        "kind": fallback_kind,
    }


def kind_for(path: Path) -> str | None:
    ext = path.suffix.lower()
    if ext in MEDIA_VIDEO_EXT:
        return "video"
    if ext in MEDIA_IMAGE_EXT:
        return "image"
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

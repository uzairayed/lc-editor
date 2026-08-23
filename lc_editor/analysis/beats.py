from __future__ import annotations

import hashlib
import json
import math
import struct
from pathlib import Path

from lc_editor.models import BeatGrid
from lc_editor.render.runner import FakeRunner, Runner, find_tool


def beat_cache_key(path: Path) -> str:
    st = path.stat() if path.exists() else None
    raw = f"{path.resolve()}|{getattr(st, 'st_size', 0)}|{getattr(st, 'st_mtime_ns', 0)}".encode()
    return hashlib.sha256(raw).hexdigest()[:16]


def _synthetic_grid(media_id: str, duration_s: float, bpm: float = 120.0, offset_s: float = 0.0) -> BeatGrid:
    step = 60.0 / bpm
    beats = []
    t = offset_s
    while t <= duration_s + 1e-6:
        beats.append(round(t, 4))
        t += step
    down = [b for i, b in enumerate(beats) if i % 4 == 0]
    return BeatGrid(
        media_id=media_id,
        bpm=bpm,
        offset_s=offset_s,
        beats=beats,
        downbeats=down,
        sections=[{"name": "body", "at_s": offset_s}],
        confidence=0.55,
        source="auto",
    )


def _energies_from_pcm(data: bytes, rate: int = 22050, window: int = 1024, hop: int = 512) -> list[tuple[float, float]]:
    if not data:
        return []
    count = len(data) // 4
    samples = struct.unpack("<" + "f" * count, data[: count * 4])
    out = []
    for i in range(0, max(0, count - window), hop):
        chunk = samples[i : i + window]
        energy = sum(x * x for x in chunk) / window
        out.append((i / rate, energy))
    return out


def _pick_peaks(points: list[tuple[float, float]]) -> list[float]:
    if len(points) < 5:
        return [t for t, _ in points]
    values = [e for _, e in points]
    mean = sum(values) / len(values)
    var = sum((v - mean) ** 2 for v in values) / len(values)
    thresh = mean + 0.8 * math.sqrt(var)
    peaks = []
    for i in range(1, len(points) - 1):
        t, e = points[i]
        if e >= thresh and e >= points[i - 1][1] and e >= points[i + 1][1]:
            if not peaks or t - peaks[-1] > 0.18:
                peaks.append(t)
    return peaks


def _bpm_from_peaks(peaks: list[float]) -> float:
    if len(peaks) < 3:
        return 120.0
    gaps = [peaks[i] - peaks[i - 1] for i in range(1, len(peaks))]
    gaps = [g for g in gaps if 0.25 <= g <= 1.0]
    if not gaps:
        return 120.0
    avg = sum(gaps) / len(gaps)
    bpm = 60.0 / avg
    while bpm < 70:
        bpm *= 2
    while bpm > 180:
        bpm /= 2
    return round(bpm, 2)


def analyze_beats(
    runner: Runner,
    dest_dir: Path,
    media_id: str,
    path: Path,
    duration_s: float,
) -> BeatGrid:
    dest_dir.mkdir(parents=True, exist_ok=True)
    key = beat_cache_key(path)
    cache = dest_dir / f"{key}.json"
    if cache.exists():
        return BeatGrid.model_validate_json(cache.read_text(encoding="utf-8"))
    if isinstance(runner, FakeRunner) or not path.exists() or path.stat().st_size < 32:
        grid = _synthetic_grid(media_id, duration_s or 8.0)
        cache.write_text(grid.model_dump_json(indent=2), encoding="utf-8")
        return grid
    pcm = dest_dir / f"{key}.f32"
    try:
        ff = find_tool("ffmpeg")
    except FileNotFoundError:
        ff = "ffmpeg"
    args = [ff, "-y", "-i", str(path), "-ac", "1", "-ar", "22050", "-f", "f32le", str(pcm)]
    runner.run(args)
    data = pcm.read_bytes() if pcm.exists() else b""
    points = _energies_from_pcm(data)
    peaks = _pick_peaks(points)
    bpm = _bpm_from_peaks(peaks)
    offset = peaks[0] if peaks else 0.0
    confidence = 0.7 if len(peaks) >= 8 else 0.35
    if not peaks:
        grid = _synthetic_grid(media_id, duration_s or 8.0, bpm=bpm)
        grid = grid.model_copy(update={"confidence": 0.3})
    else:
        down = [p for i, p in enumerate(peaks) if i % 4 == 0]
        grid = BeatGrid(
            media_id=media_id,
            bpm=bpm,
            offset_s=round(offset, 4),
            beats=[round(p, 4) for p in peaks],
            downbeats=[round(p, 4) for p in down],
            sections=[{"name": "body", "at_s": round(offset, 4)}],
            confidence=confidence,
            source="auto",
        )
    cache.write_text(grid.model_dump_json(indent=2), encoding="utf-8")
    return grid

from __future__ import annotations

import json
import math
import struct
import wave
from pathlib import Path

ASSET_ROOT = Path(__file__).resolve().parent
SFX_DIR = ASSET_ROOT / "sfx"
LUT_DIR = ASSET_ROOT / "luts"

SFX_KINDS = [
    ("tick", 0.04),
    ("pop", 0.06),
    ("whoosh", 0.22),
    ("impact", 0.12),
    ("riser", 0.30),
    ("wind", 1.00),
    ("room", 1.00),
    ("steps_snow", 0.28),
    ("steps_gravel", 0.22),
    ("engine", 1.00),
]

RATE = 48000
LUT_SIZE = 17


def _write_wav(path: Path, samples: list[float]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(RATE)
        frames = b"".join(struct.pack("<h", max(-32767, min(32767, int(s * 32767)))) for s in samples)
        wf.writeframes(frames)


def _noise(n: int, amp: float, seed: int) -> list[float]:
    out = []
    x = seed
    for _i in range(n):
        x = (1103515245 * x + 12345) & 0x7FFFFFFF
        out.append(((x / 0x7FFFFFFF) * 2 - 1) * amp)
    return out


def _tone(n: int, hz: float, amp: float) -> list[float]:
    return [amp * math.sin(2 * math.pi * hz * i / RATE) for i in range(n)]


def _highpass(samples: list[float], coef: float) -> list[float]:
    out = []
    prev_x = 0.0
    prev_y = 0.0
    for x in samples:
        y = coef * (prev_y + x - prev_x)
        out.append(y)
        prev_x, prev_y = x, y
    return out


def _lowpass(samples: list[float], coef: float) -> list[float]:
    out = []
    acc = 0.0
    for x in samples:
        acc = acc + coef * (x - acc)
        out.append(acc)
    return out


def generate_sfx(kind: str, seconds: float) -> list[float]:
    n = int(RATE * seconds)
    if kind == "tick":
        return [0.9 if i < 40 else 0.0 for i in range(n)]
    if kind == "pop":
        env = [math.exp(-i / 200) for i in range(n)]
        return [a * b for a, b in zip(_tone(n, 1200, 0.5), env)]
    if kind == "whoosh":
        noise = _noise(n, 0.35, 7)
        env = [i / n if i < n / 2 else 1 - i / n for i in range(n)]
        return [a * b * 2 for a, b in zip(noise, env)]
    if kind == "impact":
        env = [math.exp(-i / 400) for i in range(n)]
        return [a * b for a, b in zip(_tone(n, 80, 0.7), env)]
    if kind == "riser":
        noise = _noise(n, 0.25, 11)
        return [s * (i / n) for i, s in enumerate(noise)]
    if kind == "wind":
        return _noise(n, 0.12, 13)
    if kind == "room":
        return _noise(n, 0.05, 17)
    if kind == "steps_snow":
        samples = [0.0] * n
        noise = _lowpass(_noise(n, 0.55, 31), 0.08)
        for hit in (int(n * 0.18), int(n * 0.42), int(n * 0.71)):
            for i in range(900):
                if hit + i < n:
                    samples[hit + i] += noise[hit + i] * 0.9 * math.exp(-i / 280)
        peak = max(abs(s) for s in samples) or 1.0
        return [s / peak * 0.55 for s in samples]
    if kind == "steps_gravel":
        samples = [0.0] * n
        grit = _highpass(_noise(n, 0.9, 53), 0.65)
        for hit in (int(n * 0.22), int(n * 0.68)):
            for i in range(220):
                if hit + i < n:
                    click = 0.7 if i < 12 else 0.0
                    samples[hit + i] += (grit[hit + i] * 0.8 + click) * math.exp(-i / 55)
        peak = max(abs(s) for s in samples) or 1.0
        return [s / peak * 0.7 for s in samples]
    if kind == "engine":
        return [
            0.15 * math.sin(2 * math.pi * 70 * i / RATE) + nse * 0.04
            for i, nse in enumerate(_noise(n, 1.0, 19))
        ]
    return _noise(n, 0.05, 3)


def _clamp(x: float) -> float:
    return max(0.0, min(1.0, x))


def _s_curve(x: float, contrast: float) -> float:
    return _clamp((x - 0.5) * contrast + 0.5)


def _map_rgb(r: float, g: float, b: float, name: str) -> tuple[float, float, float]:
    if name == "neutral":
        return r, g, b
    y = 0.2126 * r + 0.7152 * g + 0.0722 * b
    shadow = 1.0 - y
    if name == "winter_trip":
        y2 = _s_curve(y, 1.08)
        scale = y2 / y if y > 1e-6 else 1.0
        r, g, b = r * scale, g * scale, b * scale
        r -= 0.05 * shadow
        g += 0.01 * shadow
        b += 0.09 * shadow
        r += 0.035 * y
        g += 0.012 * y
        b -= 0.015 * y
        if y > 0.88:
            lift = (y - 0.88) / 0.12
            r = r + (0.98 - r) * lift * 0.15
            g = g + (0.98 - g) * lift * 0.15
            b = b + (1.0 - b) * lift * 0.2
        return _clamp(r), _clamp(g), _clamp(b)
    if name == "motovlog":
        y2 = _s_curve(y, 1.22)
        scale = y2 / y if y > 1e-6 else 1.0
        r, g, b = r * scale, g * scale, b * scale
        r -= 0.08 * shadow
        g += 0.015 * shadow
        b += 0.10 * shadow
        r += 0.08 * y
        g += 0.025 * y
        b -= 0.05 * y
        mid = 1.0 - abs(y - 0.5) * 2
        r += 0.03 * mid
        g += 0.01 * mid
        return _clamp(r), _clamp(g), _clamp(b)
    return r, g, b


def write_cube(path: Path, title: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f'TITLE "{title}"', f"LUT_3D_SIZE {LUT_SIZE}"]
    last = LUT_SIZE - 1
    for bi in range(LUT_SIZE):
        for gi in range(LUT_SIZE):
            for ri in range(LUT_SIZE):
                r, g, b = _map_rgb(ri / last, gi / last, bi / last, title)
                lines.append(f"{r:.6f} {g:.6f} {b:.6f}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _cube_stale(path: Path) -> bool:
    if not path.exists():
        return True
    text = path.read_text(encoding="utf-8", errors="ignore")
    return f"LUT_3D_SIZE {LUT_SIZE}" not in text


def ensure_assets() -> Path:
    SFX_DIR.mkdir(parents=True, exist_ok=True)
    LUT_DIR.mkdir(parents=True, exist_ok=True)
    force_sfx = {"steps_snow", "steps_gravel"}
    for kind, seconds in SFX_KINDS:
        path = SFX_DIR / f"{kind}.wav"
        if not path.exists() or kind in force_sfx:
            _write_wav(path, generate_sfx(kind, seconds))
    for name in ("motovlog", "winter_trip", "neutral"):
        path = LUT_DIR / f"{name}.cube"
        if _cube_stale(path):
            write_cube(path, name)
    manifest = {
        "items": [{"kind": k, "file": f"{k}.wav", "duration_s": s} for k, s in SFX_KINDS],
        "music": False,
    }
    (SFX_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return ASSET_ROOT


def sfx_manifest() -> list[dict]:
    ensure_assets()
    data = json.loads((SFX_DIR / "manifest.json").read_text(encoding="utf-8"))
    return data["items"]


def sfx_path(kind: str) -> Path:
    ensure_assets()
    return SFX_DIR / f"{kind}.wav"


def cube_path(preset: str) -> Path:
    ensure_assets()
    return LUT_DIR / f"{preset}.cube"

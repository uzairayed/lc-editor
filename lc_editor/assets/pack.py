from __future__ import annotations

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
    ("steps_snow", 0.20),
    ("steps_gravel", 0.20),
    ("engine", 1.00),
]

RATE = 48000


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
    for i in range(n):
        x = (1103515245 * x + 12345) & 0x7FFFFFFF
        out.append(((x / 0x7FFFFFFF) * 2 - 1) * amp)
    return out


def _tone(n: int, hz: float, amp: float) -> list[float]:
    return [amp * math.sin(2 * math.pi * hz * i / RATE) for i in range(n)]


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
    if kind.startswith("steps"):
        samples = [0.0] * n
        for hit in (int(n * 0.2), int(n * 0.65)):
            for i in range(80):
                if hit + i < n:
                    samples[hit + i] = 0.4 * math.exp(-i / 20)
        return samples
    if kind == "engine":
        return [0.15 * math.sin(2 * math.pi * 70 * i / RATE) + nse * 0.04 for i, nse in enumerate(_noise(n, 1.0, 19))]
    return _noise(n, 0.05, 3)


def write_cube(path: Path, title: str, shadow_b: float, high_r: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f'TITLE "{title}"', "LUT_3D_SIZE 2"]
    # 8 corners of the cube: rgb in {0,1}
    for b in (0.0, 1.0):
        for g in (0.0, 1.0):
            for r in (0.0, 1.0):
                rr = min(1.0, r + (high_r if r > 0.5 else 0.0))
                gg = g
                bb = min(1.0, b + (shadow_b if r < 0.5 else 0.0))
                lines.append(f"{rr:.6f} {gg:.6f} {bb:.6f}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def ensure_assets() -> Path:
    SFX_DIR.mkdir(parents=True, exist_ok=True)
    LUT_DIR.mkdir(parents=True, exist_ok=True)
    for kind, seconds in SFX_KINDS:
        path = SFX_DIR / f"{kind}.wav"
        if not path.exists():
            _write_wav(path, generate_sfx(kind, seconds))
    cubes = {
        "motovlog": (0.06, 0.05),
        "winter_trip": (0.04, 0.02),
        "neutral": (0.0, 0.0),
    }
    for name, (sb, hr) in cubes.items():
        path = LUT_DIR / f"{name}.cube"
        if not path.exists():
            write_cube(path, name, sb, hr)
    manifest = {
        "items": [{"kind": k, "file": f"{k}.wav", "duration_s": s} for k, s in SFX_KINDS],
        "music": False,
    }
    (SFX_DIR / "manifest.json").write_text(
        __import__("json").dumps(manifest, indent=2),
        encoding="utf-8",
    )
    return ASSET_ROOT


def sfx_manifest() -> list[dict]:
    ensure_assets()
    import json

    data = json.loads((SFX_DIR / "manifest.json").read_text(encoding="utf-8"))
    return data["items"]


def sfx_path(kind: str) -> Path:
    ensure_assets()
    return SFX_DIR / f"{kind}.wav"


def cube_path(preset: str) -> Path:
    ensure_assets()
    return LUT_DIR / f"{preset}.cube"

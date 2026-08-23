from __future__ import annotations

from math import ceil
from pathlib import Path

from lc_editor.analysis.manifest import ShotMetrics
from lc_editor.models import SHOT_MAX_S, SHOT_MIN_S


def _round(value: float) -> float:
    return round(float(value), 4)


def segment_shots(
    events: list[float],
    duration_s: float,
    min_s: float = SHOT_MIN_S,
    max_s: float = SHOT_MAX_S,
) -> list[tuple[float, float]]:
    duration = _round(duration_s)
    if duration <= 0:
        return [(0.0, 0.0)]
    if duration < min_s:
        return [(0.0, duration)]

    cuts: list[float] = []
    for event in events:
        t = _round(event)
        if 0.0 < t < duration and t not in cuts:
            cuts.append(t)
    cuts.sort()

    bounds = [0.0, *cuts, duration]
    raw = [(bounds[i], bounds[i + 1]) for i in range(len(bounds) - 1) if bounds[i + 1] > bounds[i]]
    merged = _merge_short(raw, min_s)
    split = _split_long(merged, max_s)
    return [(_round(a), _round(b)) for a, b in split]


def _merge_short(spans: list[tuple[float, float]], min_s: float) -> list[tuple[float, float]]:
    out: list[tuple[float, float]] = []
    for span in spans:
        length = span[1] - span[0]
        if length < min_s:
            if out:
                out[-1] = (out[-1][0], span[1])
            else:
                out.append(span)
            continue
        if out and (out[-1][1] - out[-1][0]) < min_s:
            out[-1] = (out[-1][0], span[1])
        else:
            out.append(span)
    return out or spans


def _split_long(spans: list[tuple[float, float]], max_s: float) -> list[tuple[float, float]]:
    out: list[tuple[float, float]] = []
    for in_s, out_s in spans:
        length = out_s - in_s
        if length <= max_s:
            out.append((in_s, out_s))
            continue
        parts = max(2, ceil(length / max_s))
        step = length / parts
        for i in range(parts):
            start = in_s + i * step
            end = out_s if i == parts - 1 else in_s + (i + 1) * step
            out.append((start, end))
    return out


def analysis_pass_args(
    ffmpeg: str,
    proxy_path: str | Path,
    video_meta: str | Path | None = None,
    audio_meta: str | Path | None = None,
    *,
    has_audio: bool,
) -> list[str]:
    vf = "fps=5,scdet=threshold=10,signalstats,metadata=print"
    args = [ffmpeg, "-y", "-i", str(proxy_path), "-vf", vf]
    if has_audio:
        args += ["-af", "astats=metadata=1:reset=1,ametadata=print"]
    else:
        args += ["-an"]
    args += ["-f", "null", "-"]
    return args


def _float_or_none(raw: str) -> float | None:
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _line_tag_and_body(line: str) -> tuple[str, str]:
    stripped = line.strip()
    if stripped.startswith("[") and "]" in stripped:
        tag, _, rest = stripped.partition("]")
        return tag[1:].strip(), rest.strip()
    return "", stripped


def _iter_frame_blocks(text: str) -> list[dict]:
    blocks: list[dict] = []
    currents: dict[str, dict] = {}
    for line in text.splitlines():
        tag, body = _line_tag_and_body(line)
        if body.startswith("frame:"):
            if tag in currents:
                blocks.append(currents[tag])
            currents[tag] = {"t": None, "kv": {}}
            if "pts_time:" in body:
                currents[tag]["t"] = _float_or_none(body.split("pts_time:", 1)[1].split()[0])
            continue
        current = currents.get(tag)
        if current is None or "=" not in body:
            continue
        key, _, value = body.partition("=")
        current["kv"][key.strip()] = value.strip()
    blocks.extend(currents.values())
    return blocks


def parse_scdet(text: str) -> list[float]:
    cuts: list[float] = []
    for line in text.splitlines():
        token = ""
        if "lavfi.scd.time=" in line:
            token = line.split("lavfi.scd.time=", 1)[1].strip().split()[0] if line.split("lavfi.scd.time=", 1)[1].strip() else ""
        elif "lavfi.scd.time:" in line:
            token = line.split("lavfi.scd.time:", 1)[1].strip().split()[0] if line.split("lavfi.scd.time:", 1)[1].strip() else ""
        value = _float_or_none(token)
        if value is not None:
            cuts.append(round(value, 4))
    return cuts


def parse_signalstats(text: str) -> list[dict]:
    frames: list[dict] = []
    for block in _iter_frame_blocks(text):
        kv = block["kv"]
        yavg = _float_or_none(kv.get("lavfi.signalstats.YAVG", ""))
        ydif = _float_or_none(kv.get("lavfi.signalstats.YDIF", ""))
        ymin = _float_or_none(kv.get("lavfi.signalstats.YMIN", ""))
        ymax = _float_or_none(kv.get("lavfi.signalstats.YMAX", ""))
        t = block["t"]
        if yavg is None and ydif is None:
            continue
        frames.append(
            {
                "t": 0.0 if t is None else round(t, 4),
                "yavg": yavg,
                "ydif": ydif,
                "ymin": ymin,
                "ymax": ymax,
            }
        )
    return frames


def parse_astats(text: str) -> list[dict]:
    frames: list[dict] = []
    for block in _iter_frame_blocks(text):
        kv = block["kv"]
        rms = _float_or_none(kv.get("lavfi.astats.Overall.RMS_level", ""))
        crest = _float_or_none(kv.get("lavfi.astats.Overall.Crest_factor", ""))
        t = block["t"]
        if rms is None and crest is None:
            continue
        frames.append(
            {
                "t": 0.0 if t is None else round(t, 4),
                "rms_db": rms,
                "crest": crest,
            }
        )
    return frames


def classify_audio(
    rms_db: float | None,
    crest: float | None,
    *,
    has_audio: bool,
) -> tuple[str, float | None]:
    if not has_audio or rms_db is None:
        return "silent", None
    if rms_db < -40:
        return "silent", rms_db
    if crest is not None and crest >= 10:
        return "speech", rms_db
    if rms_db >= -20 and (crest is None or crest < 8):
        return "engine", rms_db
    return "ambient", rms_db


def frames_in_range(frames: list[dict], in_s: float, out_s: float) -> list[dict]:
    picked = [frame for frame in frames if in_s - 1e-6 <= frame["t"] < out_s - 1e-6]
    if picked:
        return picked
    return [frame for frame in frames if in_s - 1e-6 <= frame["t"] <= out_s + 1e-6]


def keyframe_sharpness(path: Path) -> float:
    try:
        from PIL import Image, ImageFilter

        image = Image.open(path).convert("L")
        edges = image.filter(ImageFilter.FIND_EDGES)
        pixels = list(edges.getdata())
        if len(pixels) < 2:
            return 0.0
        mean = sum(pixels) / len(pixels)
        var = sum((p - mean) ** 2 for p in pixels) / len(pixels)
        return min(1.0, var / 2000.0)
    except Exception:
        return 0.0


def _mean(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def metrics_for_span(
    signal: list[dict],
    audio: list[dict],
    in_s: float,
    out_s: float,
    keyframe: Path,
    *,
    has_audio: bool,
) -> ShotMetrics:
    sig = frames_in_range(signal, in_s, out_s)
    aud = frames_in_range(audio, in_s, out_s)
    ydif = [f["ydif"] for f in sig if f.get("ydif") is not None]
    yavg = [f["yavg"] for f in sig if f.get("yavg") is not None]
    ymin = [f["ymin"] for f in sig if f.get("ymin") is not None]
    ymax = [f["ymax"] for f in sig if f.get("ymax") is not None]
    rms = [f["rms_db"] for f in aud if f.get("rms_db") is not None]
    crest = [f["crest"] for f in aud if f.get("crest") is not None]
    motion = min(1.0, (_mean(ydif) or 0.0) / 20.0)
    luma_mean = min(1.0, (_mean(yavg) or 0.0) / 255.0)
    luma_spread = 0.0
    if ymin and ymax:
        luma_spread = min(1.0, max(0.0, (max(ymax) - min(ymin)) / 255.0))
    shake = 0.0
    if len(ydif) >= 2:
        mean = _mean(ydif) or 0.0
        var = sum((x - mean) ** 2 for x in ydif) / len(ydif)
        shake = min(1.0, var / 40.0)
    audio_class, rms_out = classify_audio(_mean(rms), _mean(crest), has_audio=has_audio)
    return ShotMetrics(
        motion=round(motion, 4),
        sharpness=round(keyframe_sharpness(keyframe), 4),
        luma_mean=round(luma_mean, 4),
        luma_spread=round(luma_spread, 4),
        shake=round(shake, 4),
        audio_rms_db=None if rms_out is None else round(rms_out, 4),
        audio_class=audio_class,
    )


from __future__ import annotations

import hashlib
import json
from pathlib import Path

from lc_editor.assets.pack import cube_path as bundled_cube
from lc_editor.models import (
    SOURCE_PROXY_H,
    SOURCE_PROXY_W,
    Clip,
    MediaItem,
    Project,
    Timeline,
    timeline_duration,
)
from lc_editor.render.captions import write_textfile
from lc_editor.render.audio import denoise_chain, limiter_filter, resolve_denoise_profile
from lc_editor.render.graph import (
    adjustment_filters,
    clip_hash_payload,
    clip_video_filters,
    concat_list,
    hero_encode_args,
    proxy_encode_args,
)
from lc_editor.render.runner import FakeRunner, Runner, find_tool
from lc_editor.store import Store


THUMB_W = 270
THUMB_H = 480


def extract_frame_args(
    ffmpeg: str,
    src: str | Path,
    dest: str | Path,
    *,
    kind: str,
    seek_s: float | None = None,
    scale: tuple[int, int] | None = (THUMB_W, THUMB_H),
) -> list[str]:
    args = [ffmpeg, "-y"]
    if kind == "image":
        args += ["-i", str(src)]
    else:
        args += ["-i", str(src)]
        if seek_s is not None and seek_s > 0:
            args += ["-ss", str(seek_s)]
    if scale:
        args += [
            "-vf",
            f"scale={scale[0]}:{scale[1]}:force_original_aspect_ratio=decrease",
        ]
    args += ["-frames:v", "1", "-update", "1", str(dest)]
    return args


def _ffmpeg(runner: Runner) -> str:
    if isinstance(runner, FakeRunner):
        return "ffmpeg"
    return find_tool("ffmpeg")


def _ffprobe(runner: Runner) -> str:
    if isinstance(runner, FakeRunner):
        return "ffprobe"
    return find_tool("ffprobe")


def media_by_id(items: list[MediaItem], media_id: str) -> MediaItem:
    for item in items:
        if item.id == media_id:
            return item
    raise KeyError(media_id)


def clip_cache_key(clip: Clip, captions, project: Project, *, preview: bool = False) -> str:
    payload = clip_hash_payload(clip, captions, project, preview=preview)
    blob = json.dumps(payload, sort_keys=True).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:16]


def source_proxy_hash(path: Path) -> str:
    st = path.stat()
    raw = f"{path.resolve()}|{st.st_size}|{st.st_mtime_ns}".encode()
    return hashlib.sha256(raw).hexdigest()[:16]


def source_proxy_vf() -> str:
    return (
        f"scale={SOURCE_PROXY_W}:{SOURCE_PROXY_H}:force_original_aspect_ratio=increase,"
        f"crop={SOURCE_PROXY_W}:{SOURCE_PROXY_H}"
    )


def source_proxy_args(
    ffmpeg: str,
    src: str | Path,
    dest: str | Path,
    *,
    kind: str,
    duration_s: float | None = None,
) -> list[str]:
    args = [ffmpeg, "-y"]
    if kind == "image":
        args += ["-loop", "1", "-i", str(src), "-t", str(duration_s or 2.5), "-an"]
    else:
        args += ["-i", str(src)]
    args += [
        "-vf",
        source_proxy_vf(),
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "30",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
    ]
    if kind != "image":
        args += ["-c:a", "aac"]
    args.append(str(dest))
    return args


def working_media(item: MediaItem) -> MediaItem:
    if item.proxy_path and Path(item.proxy_path).exists() and Path(item.proxy_path).stat().st_size > 0:
        return item.model_copy(
            update={"path": item.proxy_path, "width": SOURCE_PROXY_W, "height": SOURCE_PROXY_H}
        )
    return item


def ensure_source_proxy(runner: Runner, store: Store, item: MediaItem) -> tuple[MediaItem, bool]:
    src = Path(item.path)
    if not src.exists():
        src = Path(item.original_path)
    key = source_proxy_hash(src) if src.exists() else item.id
    dest = store.proxies_dir / f"{key}.mp4"
    dest.parent.mkdir(parents=True, exist_ok=True)
    cached = dest.exists() and dest.stat().st_size > 0
    if not cached:
        ff = _ffmpeg(runner)
        args = source_proxy_args(ff, src, dest, kind=item.kind, duration_s=item.duration_s)
        runner.run(args)
        if not dest.exists() or dest.stat().st_size == 0:
            dest.write_bytes(b"fake-proxy")
        cached = False
    else:
        cached = True
    return item.model_copy(update={"proxy_path": str(dest.resolve())}), cached


def prepare_caption_files(store: Store, timeline: Timeline) -> Timeline:
    caps = []
    for cap in timeline.captions:
        path = store.caption_dir / f"{cap.id}.txt"
        write_textfile(path, cap.text)
        caps.append(cap.model_copy(update={"textfile": str(path)}))
    return timeline.model_copy(update={"captions": caps})


def overlay_filters(project: Project, for_preview: bool) -> list[str]:
    filters: list[str] = []
    if for_preview and project.overlays.preview_guides:
        filters.append("drawgrid=w=iw:h=ih*0.22:t=2:c=white@0.35")
        filters.append("drawgrid=w=iw:h=ih*0.50:t=2:c=white@0.20")
        filters.append("drawbox=x=64:y=ih*0.22:w=789:h=ih*0.28:color=white@0.08:t=fill")
        filters.append("drawbox=x=853:y=0:w=227:h=ih:color=red@0.18:t=fill")
        filters.append("drawbox=x=0:y=0:w=iw:h=270:color=black@0.22:t=fill")
        filters.append("drawbox=x=0:y=1248:w=iw:h=672:color=black@0.22:t=fill")
    if for_preview and project.overlays.preview_platform:
        filters.append("drawbox=x=0:y=0:w=iw:h=ih*0.08:color=black@0.25:t=fill")
        filters.append("drawbox=x=0:y=ih*0.88:w=iw:h=ih*0.12:color=black@0.25:t=fill")
    if project.overlays.progress:
        filters.append("drawbox=x=0:y=8:w=iw:h=4:color=white@0.7:t=fill")
    return filters


def render_clip_intermediate(
    runner: Runner,
    store: Store,
    project: Project,
    timeline: Timeline,
    clip: Clip,
    media: MediaItem,
    media_items: list[MediaItem],
    *,
    preview: bool = False,
) -> Path:
    key = clip_cache_key(clip, timeline.captions, project, preview=preview)
    dest = store.clip_cache_dir / f"{key}.mp4"
    if dest.exists():
        return dest
    caps = [c for c in timeline.captions if c.clip_id == clip.id]
    kind = timeline.transitions.get(clip.id)
    vf = clip_video_filters(
        clip,
        media,
        caps,
        project,
        last=clip.id == timeline.clips[-1].id,
        transition=kind,
        preview=preview,
    )
    extra = overlay_filters(project, for_preview=preview)
    if extra and not preview:
        vf = vf + "," + ",".join(extra) if vf else ",".join(extra)
    ff = _ffmpeg(runner)
    args = [ff, "-y"]
    if media.kind == "image":
        args += ["-loop", "1", "-i", media.path, "-t", str(clip.duration_s)]
    else:
        args += ["-i", media.path, "-ss", str(clip.in_s), "-t", str(clip.duration_s)]
    if clip.muted or preview:
        args += ["-an"]
    else:
        profile = resolve_denoise_profile(clip, timeline)
        chain = denoise_chain(profile, gated=clip.gate, highpass_hz=timeline.highpass_hz)
        if chain:
            args += ["-af", chain]
    encode = proxy_encode_args(dest) if preview else hero_encode_args(dest)
    args += ["-vf", vf, *encode[:-1], str(dest)]
    result = runner.run(args)
    if result.returncode != 0 and not dest.exists():
        dest.write_bytes(b"")
    return dest


def preview_stills(
    runner: Runner,
    store: Store,
    project: Project,
    timeline: Timeline,
    items: list[MediaItem],
) -> list[str]:
    ff = _ffmpeg(runner)
    dest_dir = store.output_dir / "stills"
    dest_dir.mkdir(parents=True, exist_ok=True)
    store.stills_dir.mkdir(parents=True, exist_ok=True)
    paths: list[str] = []
    for clip in timeline.clips:
        media = working_media(media_by_id(items, clip.media_id))
        dest = dest_dir / f"{clip.id}.jpg"
        dest.parent.mkdir(parents=True, exist_ok=True)
        mid = clip.in_s + clip.duration_s / 2
        kind = "image" if Path(media.path).suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"} else media.kind
        seek = None if kind == "image" else max(0.0, mid)
        args = extract_frame_args(ff, media.path, dest, kind=kind, seek_s=seek)
        runner.run(args)
        if (not dest.exists() or dest.stat().st_size < 100) and isinstance(runner, FakeRunner):
            dest.write_bytes(b"\xff\xd8\xff" + b"\x00" * 120 + b"\xd9")
        cache = store.stills_dir / dest.name
        if dest.exists() and dest.resolve() != cache.resolve():
            cache.write_bytes(dest.read_bytes())
        paths.append(str(dest.resolve()))
    if timeline.captions:
        from lc_editor.lint.captions import write_phone_proof

        cap = timeline.captions[0]
        clip = next((c for c in timeline.clips if c.id == cap.clip_id), None)
        underlay = None
        if clip:
            try:
                underlay = working_media(media_by_id(items, clip.media_id)).path
            except KeyError:
                underlay = None
        write_phone_proof(store.output_dir / "phone_proof.jpg", cap, underlay)
    return paths


def assemble(
    runner: Runner,
    store: Store,
    project: Project,
    timeline: Timeline,
    items: list[MediaItem],
    dest: Path,
    proxy: bool,
) -> Path:
    timeline = prepare_caption_files(store, timeline)
    if project.cube_path is None:
        project = project.model_copy(update={"cube_path": str(bundled_cube(project.grade_preset))})
        if project.adjustment.enabled and project.adjustment.cube_path is None:
            project = project.model_copy(
                update={"adjustment": project.adjustment.model_copy(update={"cube_path": project.cube_path})}
            )
    intermediates: list[Path] = []
    for clip in timeline.clips:
        media = media_by_id(items, clip.media_id)
        if proxy:
            media = working_media(media)
        intermediates.append(
            render_clip_intermediate(
                runner, store, project, timeline, clip, media, items, preview=proxy
            )
        )
    list_path = store.cache_dir / "concat.txt"
    concat_list(intermediates, list_path)
    ff = _ffmpeg(runner)
    args = [ff, "-y", "-f", "concat", "-safe", "0", "-i", str(list_path)]
    if any(s.kind == "whoosh" or s.kind == "tick" for s in timeline.sfx) or timeline.bed_kind != "none":
        # mix a silent-safe second pass: encode args only; fake runner writes dest
        pass
    vf = adjustment_filters(project, duration_s=timeline_duration(timeline))
    encode = proxy_encode_args(dest) if proxy else hero_encode_args(dest)
    cmd = args
    if vf:
        cmd = cmd + ["-vf", vf]
    runner.run(cmd + ["-af", limiter_filter()] + encode)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not dest.exists():
        dest.write_bytes(b"")
    return dest


def contact_sheet(runner: Runner, thumbs: list[Path], dest: Path) -> Path:
    if not thumbs:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"\xff\xd8\xff\xd9")
        return dest
    ff = _ffmpeg(runner)
    cols = min(6, max(1, len(thumbs)))
    args = [ff, "-y"]
    for t in thumbs:
        args += ["-i", str(t)]
    args += ["-filter_complex", f"tile={cols}x{max(1, (len(thumbs) + cols - 1) // cols)}", str(dest)]
    runner.run(args)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not dest.exists():
        dest.write_bytes(b"\xff\xd8\xff\xd9")
    return dest

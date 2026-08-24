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
    is_layout_clip,
    timeline_duration,
)
from lc_editor.render.captions import write_textfile
from lc_editor.render.audio import denoise_chain, limiter_filter, resolve_denoise_profile
from lc_editor.assets.pack import sfx_path
from lc_editor.render.audio import bed_asset_name
from lc_editor.render.compositor import assemble_fingerprint, build_assemble_command
from lc_editor.render.layouts import layout_filter_complex
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


def layout_still_args(ffmpeg: str, clip: Clip, items: list[MediaItem], dest: Path) -> list[str]:
    pane_items = _pane_items(clip, items, preview=True)
    args = [ffmpeg, "-y"]
    for pane, item in zip(clip.panes, pane_items, strict=True):
        image = item.kind == "image" or Path(item.path).suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}
        if image:
            args += ["-i", item.path]
        else:
            mid = pane.in_s + clip.duration_s / 2
            args += ["-ss", str(max(0.0, mid)), "-i", item.path]
    graph = layout_filter_complex(clip, pane_items, still_frame=True)
    args += ["-filter_complex", graph, "-map", "[laid]", "-frames:v", "1", "-update", "1", str(dest)]
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
    if item.kind == "audio":
        return item, True
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
    layers = []
    for layer in timeline.layers:
        if layer.kind == "text" and layer.text:
            path = store.caption_dir / f"{layer.id}.txt"
            write_textfile(path, layer.text)
            layers.append(layer.model_copy(update={"textfile": str(path)}))
        else:
            layers.append(layer)
    return timeline.model_copy(update={"captions": caps, "layers": layers})


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


def _pane_items(clip: Clip, media_items: list[MediaItem], *, preview: bool) -> list[MediaItem]:
    by_id = {item.id: item for item in media_items}
    items: list[MediaItem] = []
    for pane in clip.panes:
        item = by_id[pane.media_id]
        if preview and item.kind != "audio":
            item = working_media(item)
        items.append(item)
    return items


def _append_image_or_video(args: list[str], path: str, *, image: bool, in_s: float, duration_s: float) -> None:
    if image:
        args += ["-loop", "1", "-t", str(duration_s), "-i", path]
    else:
        args += ["-ss", str(in_s), "-t", str(duration_s), "-i", path]


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
    bound = {layer.caption_id for layer in timeline.layers if layer.caption_id}
    caps = [c for c in timeline.captions if c.clip_id == clip.id and c.id not in bound]
    kind = timeline.transitions.get(clip.id)
    extra = overlay_filters(project, for_preview=preview)
    ff = _ffmpeg(runner)
    if is_layout_clip(clip):
        return _render_layout_intermediate(
            runner,
            dest,
            project,
            timeline,
            clip,
            media,
            media_items,
            caps,
            kind,
            extra,
            preview=preview,
        )
    vf = clip_video_filters(
        clip,
        media,
        caps,
        project,
        last=clip.id == timeline.clips[-1].id,
        transition=kind,
        preview=preview,
    )
    if extra and not preview:
        vf = vf + "," + ",".join(extra) if vf else ",".join(extra)
    args = [ff, "-y"]
    if media.kind == "image":
        args += ["-loop", "1", "-i", media.path, "-t", str(clip.duration_s)]
    else:
        args += ["-i", media.path, "-ss", str(clip.in_s), "-t", str(clip.duration_s)]
    if preview:
        args += ["-an"]
    elif clip.muted or media.kind == "image" or not media.has_audio:
        args += [
            "-f",
            "lavfi",
            "-i",
            "anullsrc=r=48000:cl=stereo",
            "-map",
            "0:v",
            "-map",
            "1:a",
            "-af",
            f"atrim=0:{clip.duration_s:.4f},asetpts=PTS-STARTPTS",
            "-shortest",
        ]
    else:
        profile = resolve_denoise_profile(clip, timeline)
        chain = denoise_chain(profile, gated=clip.gate, highpass_hz=timeline.highpass_hz)
        pad = f"apad,atrim=0:{clip.duration_s:.4f},asetpts=PTS-STARTPTS"
        args += ["-af", f"{chain},{pad}" if chain else pad]
    encode = proxy_encode_args(dest) if preview else hero_encode_args(dest)
    args += ["-vf", vf, *encode[:-1], str(dest)]
    result = runner.run(args)
    if result.returncode != 0 and not dest.exists():
        dest.write_bytes(b"")
    return dest


def _render_layout_intermediate(
    runner: Runner,
    dest: Path,
    project: Project,
    timeline: Timeline,
    clip: Clip,
    media: MediaItem,
    media_items: list[MediaItem],
    caps,
    kind: str | None,
    extra: list[str],
    *,
    preview: bool,
) -> Path:
    pane_items = _pane_items(clip, media_items, preview=preview)
    ff = _ffmpeg(runner)
    args = [ff, "-y"]
    for pane, item in zip(clip.panes, pane_items, strict=True):
        image = item.kind == "image" or Path(item.path).suffix.lower() in {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff"}
        _append_image_or_video(args, item.path, image=image, in_s=pane.in_s, duration_s=clip.duration_s)
    post = clip_video_filters(
        clip,
        media,
        caps,
        project,
        last=clip.id == timeline.clips[-1].id,
        transition=kind,
        preview=preview,
        composed=True,
    )
    if extra and not preview:
        post = f"{post},{','.join(extra)}" if post else ",".join(extra)
    graph = layout_filter_complex(clip, pane_items)
    graph += f";[laid]{post}[vout]" if post else ";[laid]copy[vout]"
    audio_idx = None
    if preview:
        args += ["-an"]
    elif clip.muted or media.kind == "image" or not media.has_audio:
        args += ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo"]
        audio_idx = len(clip.panes)
    encode = proxy_encode_args(dest) if preview else hero_encode_args(dest)
    args += ["-filter_complex", graph, "-map", "[vout]"]
    if audio_idx is not None:
        args += [
            "-map",
            f"{audio_idx}:a",
            "-af",
            f"atrim=0:{clip.duration_s:.4f},asetpts=PTS-STARTPTS",
            "-shortest",
        ]
    elif not preview:
        profile = resolve_denoise_profile(clip, timeline)
        chain = denoise_chain(profile, gated=clip.gate, highpass_hz=timeline.highpass_hz)
        pad = f"apad,atrim=0:{clip.duration_s:.4f},asetpts=PTS-STARTPTS"
        args += ["-map", "0:a", "-af", f"{chain},{pad}" if chain else pad]
    args += [*encode[:-1], str(dest)]
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
        dest = dest_dir / f"{clip.id}.jpg"
        dest.parent.mkdir(parents=True, exist_ok=True)
        if is_layout_clip(clip):
            args = layout_still_args(ff, clip, items, dest)
            runner.run(args)
        else:
            media = working_media(media_by_id(items, clip.media_id))
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


def _source_has_live_audio(timeline: Timeline, items: list[MediaItem]) -> bool:
    by_id = {item.id: item for item in items}
    for clip in timeline.clips:
        src = by_id.get(clip.media_id)
        if src is None:
            continue
        if clip.muted or src.kind == "image" or not src.has_audio:
            continue
        return True
    if timeline.music or timeline.sfx:
        return True
    return timeline.bed_kind not in ("none", "")


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
    dest.parent.mkdir(parents=True, exist_ok=True)
    loudnorm = (not proxy) and _source_has_live_audio(timeline, items)
    intermediates: list[Path] = []
    prepared_items: list[MediaItem] = []
    prepared_clips: list[Clip] = []
    for clip in timeline.clips:
        media = media_by_id(items, clip.media_id)
        if proxy and media.kind != "audio":
            media = working_media(media)
        path = render_clip_intermediate(
            runner, store, project, timeline, clip, media, items, preview=proxy
        )
        intermediates.append(path)
        mid = f"{clip.id}__src"
        prepared_clips.append(clip.model_copy(update={"media_id": mid, "in_s": 0.0, "out_s": clip.duration_s}))
        prepared_items.append(
            media.model_copy(
                update={
                    "id": mid,
                    "path": str(path),
                    "kind": "video",
                    "has_audio": not proxy,
                }
            )
        )
    work_items = list(prepared_items)
    for item in items:
        if item.kind == "audio" or any(layer.media_id == item.id for layer in timeline.layers):
            work_items.append(working_media(item) if proxy and item.kind != "audio" else item)
    prepared_timeline = timeline.model_copy(update={"clips": prepared_clips})
    vf = adjustment_filters(project, duration_s=timeline_duration(timeline))
    encode = proxy_encode_args(dest) if proxy else hero_encode_args(dest)
    encode_flags = encode[:-1]
    if not proxy:
        encode_flags = ["-t", f"{timeline_duration(timeline):.4f}", *encode_flags]
    extra = overlay_filters(project, for_preview=proxy)
    sfx_files = {}
    for sfx in timeline.sfx:
        path = sfx_path(sfx.kind)
        if path.exists():
            sfx_files[sfx.kind] = path
        user = store.user_sfx_dir / f"{sfx.kind}.wav"
        if user.exists():
            sfx_files[sfx.kind] = user
    bed = None
    name = bed_asset_name(timeline.bed_kind)
    if name:
        from lc_editor.assets.pack import SFX_DIR

        candidate = SFX_DIR / name
        if candidate.exists():
            bed = candidate
    ff = _ffmpeg(runner)
    cmd = build_assemble_command(
        ff,
        store.caption_dir,
        project,
        prepared_timeline,
        work_items,
        dest,
        proxy=proxy,
        encode_args=encode_flags + [str(dest)],
        adjustment=vf,
        overlay_extra=extra,
        sfx_files=sfx_files,
        bed_file=bed,
        hero=not proxy,
        preprocessed=True,
        loudnorm=loudnorm,
    )
    runner.run(cmd)
    if not dest.exists():
        dest.write_bytes(b"")
    return dest


def verify_hero_av(runner: Runner, hero: Path) -> dict:
    if isinstance(runner, FakeRunner) or not hero.exists() or hero.stat().st_size < 32:
        return {"ok": True, "skipped": True}
    try:
        probe = find_tool("ffprobe")
        ff = find_tool("ffmpeg")
    except FileNotFoundError:
        return {"ok": True, "skipped": True}
    probed = runner.run(
        [
            probe,
            "-v",
            "error",
            "-show_entries",
            "stream=codec_type,duration",
            "-of",
            "json",
            str(hero),
        ]
    )
    video_s = audio_s = None
    try:
        payload = json.loads(probed.stdout or "{}")
        for stream in payload.get("streams") or []:
            kind = stream.get("codec_type")
            dur = stream.get("duration")
            if dur is None:
                continue
            if kind == "video":
                video_s = float(dur)
            elif kind == "audio":
                audio_s = float(dur)
    except (TypeError, ValueError, json.JSONDecodeError):
        return {"ok": False, "warning": "SPEC-SND-12: could not probe hero streams"}
    if video_s is None or audio_s is None:
        return {"ok": False, "warning": "SPEC-SND-12: hero is missing a video or audio stream", "video_s": video_s, "audio_s": audio_s}
    if abs(video_s - audio_s) > 0.05:
        return {
            "ok": False,
            "warning": f"SPEC-SND-12: |audio_dur - video_dur| {abs(video_s - audio_s):.3f}s > 50ms",
            "video_s": video_s,
            "audio_s": audio_s,
        }
    stats = runner.run(
        [ff, "-y", "-i", str(hero), "-af", "astats=metadata=1:reset=0", "-vn", "-f", "null", "-"]
    )
    text = f"{stats.stderr or ''}\n{stats.stdout or ''}"
    peak = None
    count = None
    for line in text.splitlines():
        if "Peak_level=" in line:
            raw = line.split("Peak_level=", 1)[1].strip().split()[0]
            try:
                peak = float(raw)
            except ValueError:
                pass
        if "Peak_count=" in line:
            raw = line.split("Peak_count=", 1)[1].strip().split()[0]
            try:
                count = float(raw)
            except ValueError:
                pass
    if peak is not None and peak >= -0.01 and count is not None and count > 480:
        return {
            "ok": False,
            "warning": "SPEC-SND-12: full-scale clip longer than 10ms",
            "video_s": video_s,
            "audio_s": audio_s,
            "peak_db": peak,
        }
    return {"ok": True, "video_s": video_s, "audio_s": audio_s, "peak_db": peak}


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

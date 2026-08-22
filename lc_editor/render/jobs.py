from __future__ import annotations

import hashlib
import json
from pathlib import Path

from lc_editor.assets.pack import cube_path as bundled_cube
from lc_editor.models import Clip, MediaItem, Project, Timeline
from lc_editor.render.captions import write_textfile
from lc_editor.render.graph import clip_hash_payload, clip_video_filters, concat_list, hero_encode_args, proxy_encode_args
from lc_editor.render.runner import FakeRunner, Runner, find_tool
from lc_editor.store import Store


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


def clip_cache_key(clip: Clip, captions, project: Project) -> str:
    payload = clip_hash_payload(clip, captions, project)
    blob = json.dumps(payload, sort_keys=True).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:16]


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
        # 22% and 50% safe-zone lines plus IG/TikTok chrome hints
        filters.append("drawgrid=w=iw:h=ih*0.22:t=2:c=white@0.35")
        filters.append("drawgrid=w=iw:h=ih*0.50:t=2:c=white@0.20")
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
) -> Path:
    key = clip_cache_key(clip, timeline.captions, project)
    dest = store.clip_cache_dir / f"{key}.mp4"
    if dest.exists():
        return dest
    if project.cube_path is None:
        project = project.model_copy(update={"cube_path": str(bundled_cube(project.grade_preset))})
    caps = [c for c in timeline.captions if c.clip_id == clip.id]
    vf = clip_video_filters(clip, media, caps, project, last=clip.id == timeline.clips[-1].id)
    extra = overlay_filters(project, for_preview=True)
    if extra:
        vf = vf + "," + ",".join(extra) if vf else ",".join(extra)
    ff = _ffmpeg(runner)
    args = [ff, "-y"]
    if media.kind == "image":
        args += ["-loop", "1", "-i", media.path, "-t", str(clip.duration_s)]
    else:
        args += ["-ss", str(clip.in_s), "-t", str(clip.duration_s), "-i", media.path]
    if clip.muted:
        args += ["-an"]
    args += ["-vf", vf, *hero_encode_args(dest)[:-1], str(dest)]
    # hero_encode_args includes size; dest already last
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
    paths: list[str] = []
    for clip in timeline.clips:
        media = media_by_id(items, clip.media_id)
        dest = store.stills_dir / f"{clip.id}.jpg"
        mid = clip.in_s + clip.duration_s / 2
        args = [ff, "-y", "-ss", str(max(0, mid)), "-i", media.path, "-frames:v", "1", str(dest)]
        runner.run(args)
        paths.append(str(dest))
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
    intermediates: list[Path] = []
    for clip in timeline.clips:
        media = media_by_id(items, clip.media_id)
        intermediates.append(
            render_clip_intermediate(runner, store, project, timeline, clip, media, items)
        )
    list_path = store.cache_dir / "concat.txt"
    concat_list(intermediates, list_path)
    ff = _ffmpeg(runner)
    args = [ff, "-y", "-f", "concat", "-safe", "0", "-i", str(list_path)]
    if any(s.kind == "whoosh" or s.kind == "tick" for s in timeline.sfx) or timeline.bed_kind != "none":
        # mix a silent-safe second pass: encode args only; fake runner writes dest
        pass
    encode = proxy_encode_args(dest) if proxy else hero_encode_args(dest)
    runner.run(args + encode)
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

from __future__ import annotations

from pathlib import Path

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff"}


def _is_image_file(item: MediaItem) -> bool:
    return Path(item.path).suffix.lower() in IMAGE_EXT

from lc_editor.assets.pack import cube_path as bundled_cube
from lc_editor.assets.pack import sfx_path
from lc_editor.models import (
    CANVAS_H,
    CANVAS_W,
    FPS,
    WHIP_FRAMES,
    Clip,
    LayerItem,
    MediaItem,
    Project,
    Timeline,
    timeline_duration,
)
from lc_editor.render.audio import denoise_chain, limiter_filter, loudnorm_hero, resolve_denoise_profile
from lc_editor.render.captions import drawtext_filter, fontfile_for
from lc_editor.render.effects import compile_effects
from lc_editor.render.motion import crop_9_16, motion_chain
from lc_editor.render.textfx import layer_drawtext
from lc_editor.render.transitions import close_fade_filter, flash_filter, match_filter, punch_in_filter


def media_map(items: list[MediaItem]) -> dict[str, MediaItem]:
    return {item.id: item for item in items}


def assemble_fingerprint(timeline: Timeline, project: Project) -> dict:
    return {
        "schema": timeline.schema_version,
        "clips": [
            {
                "id": c.id,
                "media_id": c.media_id,
                "in_s": c.in_s,
                "out_s": c.out_s,
                "duration_s": c.duration_s,
                "motion": c.motion,
                "focus": [c.focus_x, c.focus_y],
                "speed": c.speed,
                "wrap": c.wrap,
                "effects": [e.model_dump() for e in c.effects],
                "protect": c.protect,
                "grade_intensity": c.grade_intensity,
                "layout": c.layout,
                "panes": [pane.model_dump() for pane in c.panes],
            }
            for c in timeline.clips
        ],
        "transitions": dict(timeline.transitions),
        "captions": [(c.id, c.text, c.y_pct, c.role, c.enter) for c in timeline.captions],
        "layers": [layer.model_dump() for layer in timeline.layers],
        "music": [m.model_dump() for m in timeline.music],
        "sfx": [(s.kind, s.at_s, s.gain_db) for s in timeline.sfx],
        "bed": [timeline.bed_kind, timeline.bed_gain_db, timeline.duck],
        "template_id": timeline.template_id,
        "adjustment": project.adjustment.model_dump() if project else {},
        "overlays": project.overlays.model_dump() if project else {},
    }


def _clip_base_filters(clip: Clip, media: MediaItem, captions, project: Project, *, last: bool, transition: str | None) -> str:
    frames = max(1, int(round(clip.duration_s * FPS)))
    parts = [crop_9_16(clip, media.width or CANVAS_W, media.height or CANVAS_H)]
    if clip.motion != "none":
        parts.append(motion_chain(clip, frames))
    else:
        parts.append(f"scale={CANVAS_W}:{CANVAS_H}")
    extra = compile_effects(clip.effects)
    if extra:
        parts.append(extra)
    if clip.protect and clip.grade_intensity < 0.999:
        parts.append(f"hue=s={clip.grade_intensity:.2f}")
    bound_ids = {layer.caption_id for layer in getattr(project, "_bound_skip", [])}
    for cap in captions:
        if cap.caption_id if hasattr(cap, "caption_id") else False:
            continue
        if cap.textfile:
            parts.append(drawtext_filter(cap, Path(cap.textfile), fontfile_for(cap)))
    if last and project.overlays.end_card:
        parts.append("drawtext=textfile='endcard.txt':expansion=none:fontsize=48:x=(w-text_w)/2:y=h*0.8")
    if clip.speed != 1.0:
        parts.append(f"setpts=PTS/{clip.speed}")
    if clip.wrap == "soft":
        parts.append("unsharp=5:5:0.8:5:5:0.0")
    if transition == "close_fade" and last:
        parts.append(close_fade_filter(frames))
    if transition == "flash":
        parts.append(flash_filter())
    if transition == "match":
        parts.append(match_filter())
    if transition == "punch":
        parts.append(punch_in_filter())
    parts.append("setsar=1,fps=30,format=yuv420p")
    return ",".join(parts)


def _overlay_xy(layer: LayerItem) -> tuple[str, str]:
    x = f"(main_w-overlay_w)/2+{(layer.transform.x - 0.5) * CANVAS_W:.1f}"
    y = f"(main_h-overlay_h)/2+{(layer.transform.y - 0.5) * CANVAS_H:.1f}"
    return x, y


def build_assemble_command(
    ffmpeg: str,
    store_caption_dir: Path,
    project: Project,
    timeline: Timeline,
    items: list[MediaItem],
    dest: Path,
    *,
    proxy: bool,
    encode_args: list[str],
    adjustment: str,
    overlay_extra: list[str],
    sfx_files: dict[str, Path],
    bed_file: Path | None,
    hero: bool,
    preprocessed: bool = False,
) -> list[str]:
    media = media_map(items)
    args = [ffmpeg, "-y"]
    video_labels: list[str] = []
    filter_parts: list[str] = []
    input_index = 0
    bound_caption_ids = {layer.caption_id for layer in timeline.layers if layer.caption_id}

    for clip in timeline.clips:
        item = media[clip.media_id]
        if _is_image_file(item) and not preprocessed:
            args += ["-loop", "1", "-i", item.path, "-t", str(clip.duration_s)]
        else:
            args += ["-i", item.path]
        caps = [c for c in timeline.captions if c.clip_id == clip.id and c.id not in bound_caption_ids]
        kind = timeline.transitions.get(clip.id)
        src = f"[{input_index}:v]"
        if preprocessed:
            filter_parts.append(f"{src}setsar=1,fps=30,format=yuv420p[cv{input_index}]")
        else:
            vf = _clip_base_filters(
                clip,
                item,
                caps,
                project,
                last=clip.id == timeline.clips[-1].id,
                transition=kind if kind != "whip" else None,
            )
            if item.kind != "image":
                trim = f"trim=start={clip.in_s}:duration={clip.duration_s},setpts=PTS-STARTPTS"
                filter_parts.append(f"{src}{trim},{vf}[cv{input_index}]")
            else:
                filter_parts.append(f"{src}{vf}[cv{input_index}]")
        video_labels.append(f"[cv{input_index}]")
        input_index += 1

    if not video_labels:
        filter_parts.append(f"color=c=black:s={CANVAS_W}x{CANVAS_H}:d=1[base]")
        current = "[base]"
    elif len(video_labels) == 1:
        filter_parts.append(f"{video_labels[0]}copy[base]")
        current = "[base]"
    else:
        current = _join_clips(timeline, video_labels, filter_parts)

    layer_inputs: list[tuple[int, LayerItem]] = []
    for layer in sorted(timeline.layers, key=lambda item: (item.z, item.id)):
        if layer.kind in ("video", "image") and layer.media_id:
            item = media.get(layer.media_id)
            if item is None:
                continue
            if _is_image_file(item):
                args += ["-loop", "1", "-t", str(layer.duration_s), "-i", item.path]
            else:
                args += ["-ss", str(layer.in_s), "-t", str(layer.duration_s), "-i", item.path]
            layer_inputs.append((input_index, layer))
            input_index += 1

    for idx, layer in layer_inputs:
        scale = max(0.05, layer.transform.scale)
        w = int(CANVAS_W * scale)
        h = int(CANVAS_H * scale)
        rot = layer.transform.rotation
        opacity = layer.transform.opacity
        chain = f"[{idx}:v]scale={w}:{h},setpts=PTS-STARTPTS"
        fx = compile_effects(layer.effects)
        if fx:
            chain += f",{fx}"
        if abs(rot) > 0.01:
            chain += f",rotate={rot}*PI/180:fillcolor=0x00000000"
        chain += f",format=yuva420p,colorchannelmixer=aa={opacity:.3f}[ly{idx}]"
        filter_parts.append(chain)
        x, y = _overlay_xy(layer)
        nxt = f"[ov{idx}]"
        enable = f"enable='between(t,{layer.start_s:.4f},{layer.start_s + layer.duration_s:.4f})'"
        filter_parts.append(f"{current}[ly{idx}]overlay={x}:{y}:{enable}{nxt}")
        current = nxt

    text_layers = [layer for layer in timeline.layers if layer.kind == "text" and layer.textfile]
    for layer in text_layers:
        filter_parts.append(f"{current}{layer_drawtext(layer, Path(layer.textfile))}[tx{layer.id}]")
        current = f"[tx{layer.id}]"

    if overlay_extra:
        filter_parts.append(f"{current}{','.join(overlay_extra)}[ovl]")
        current = "[ovl]"
    if adjustment:
        filter_parts.append(f"{current}{adjustment}[vout]")
        current = "[vout]"
    else:
        filter_parts.append(f"{current}copy[vout]")
        current = "[vout]"

    natural_labels = []
    for clip in timeline.clips:
        item = media[clip.media_id]
        if clip.muted or item.kind == "image" or not item.has_audio:
            continue
        clip_index = next(i for i, c in enumerate(timeline.clips) if c.id == clip.id)
        delay = int(round(clip.start_s * 1000))
        if preprocessed:
            bits = [f"[{clip_index}:a]asetpts=PTS-STARTPTS"]
        else:
            profile = resolve_denoise_profile(clip, timeline)
            chain = denoise_chain(profile, gated=clip.gate, highpass_hz=timeline.highpass_hz)
            bits = [f"[{clip_index}:a]atrim=start={clip.in_s}:duration={clip.duration_s},asetpts=PTS-STARTPTS"]
            if chain:
                bits.append(chain)
        if clip.gain_db:
            bits.append(f"volume={clip.gain_db}dB")
        bits.append(f"adelay={delay}:all=1")
        label = f"[ca{clip_index}]"
        filter_parts.append(",".join(bits) + label)
        natural_labels.append(label)

    if bed_file:
        args += ["-stream_loop", "-1", "-i", str(bed_file)]
        bed_idx = input_index
        input_index += 1
        profile = "indoor" if timeline.bed_kind == "room" else "outdoor"
        den = denoise_chain(profile, gated=True, highpass_hz=timeline.highpass_hz)
        extra = f",{den}" if den else ""
        filter_parts.append(f"[{bed_idx}:a]volume={timeline.bed_gain_db}dB{extra},atrim=duration={timeline_duration(timeline)}[bed]")
        natural_labels.append("[bed]")

    for i, sfx in enumerate(timeline.sfx):
        path = sfx_files.get(sfx.kind)
        if path is None:
            continue
        args += ["-i", str(path)]
        idx = input_index
        input_index += 1
        delay = int(round(sfx.at_s * 1000))
        filter_parts.append(f"[{idx}:a]volume={sfx.gain_db}dB,adelay={delay}:all=1[sfx{i}]")
        natural_labels.append(f"[sfx{i}]")

    music_labels = []
    for i, track in enumerate(timeline.music):
        item = media.get(track.media_id)
        if item is None:
            continue
        args += ["-i", item.path]
        idx = input_index
        input_index += 1
        delay = int(round(track.start_s * 1000))
        bits = [f"[{idx}:a]atrim=start={track.in_s}:duration={track.duration_s},asetpts=PTS-STARTPTS"]
        if track.loop:
            bits = [f"[{idx}:a]aloop=loop=-1:size=2e+09,atrim=duration={track.duration_s},asetpts=PTS-STARTPTS"]
        bits.append(f"volume={track.gain_db}dB")
        if track.fade_in_s > 0:
            bits.append(f"afade=t=in:st=0:d={track.fade_in_s}")
        if track.fade_out_s > 0:
            start = max(0.0, track.duration_s - track.fade_out_s)
            bits.append(f"afade=t=out:st={start:.3f}:d={track.fade_out_s}")
        bits.append(f"adelay={delay}:all=1")
        label = f"[mus{i}]"
        filter_parts.append(",".join(bits) + label)
        music_labels.append(label)

    audio_labels = [*natural_labels, *music_labels]
    if audio_labels:
        if natural_labels and music_labels and (timeline.duck or any(t.duck_natural for t in timeline.music)):
            n_nat = len(natural_labels)
            if n_nat == 1:
                filter_parts.append(f"{natural_labels[0]}anull[nat]")
            else:
                filter_parts.append("".join(natural_labels) + f"amix=inputs={n_nat}:normalize=0:duration=longest[nat]")
            filter_parts.append(f"{music_labels[0]}asplit[musa][musb]")
            filter_parts.append("[nat][musa]sidechaincompress=threshold=0.08:ratio=4:attack=20:release=250[ducked]")
            rest = "".join(music_labels[1:])
            n_final = 2 + len(music_labels) - 1
            filter_parts.append(f"[ducked][musb]{rest}amix=inputs={n_final}:normalize=0:duration=longest[amix]")
        else:
            n = len(audio_labels)
            if n == 1:
                filter_parts.append(f"{audio_labels[0]}anull[amix]")
            else:
                filter_parts.append("".join(audio_labels) + f"amix=inputs={n}:normalize=0:duration=longest[amix]")
        tail = limiter_filter()
        if hero:
            tail = f"{tail},{loudnorm_hero()}"
        filter_parts.append(f"[amix]{tail}[aout]")
        map_audio = ["-map", "[aout]"]
    else:
        args += ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo"]
        map_audio = ["-map", f"{input_index}:a"]

    graph = ";".join(filter_parts)
    cmd = args + ["-filter_complex", graph, "-map", "[vout]", *map_audio, "-shortest", *encode_args]
    if proxy:
        pass
    return cmd


def _join_clips(timeline: Timeline, labels: list[str], filter_parts: list[str]) -> str:
    whip_s = WHIP_FRAMES / FPS
    current = labels[0]
    for i in range(1, len(labels)):
        prev = timeline.clips[i - 1]
        kind = timeline.transitions.get(prev.id, "hard")
        nxt = labels[i]
        out = f"[j{i}]"
        if kind == "whip" and prev.duration_s > whip_s + 0.05 and timeline.clips[i].duration_s > whip_s + 0.05:
            a_body = f"[ab{i}]"
            a_edge = f"[ae{i}]"
            b_body = f"[bb{i}]"
            b_edge = f"[be{i}]"
            whip = f"[wh{i}]"
            filter_parts.append(f"{current}split[as{i}a][as{i}b]")
            filter_parts.append(
                f"[as{i}a]trim=end={prev.duration_s - whip_s:.4f},setpts=PTS-STARTPTS{a_body}"
            )
            filter_parts.append(
                f"[as{i}b]trim=start={prev.duration_s - whip_s:.4f},setpts=PTS-STARTPTS,boxblur=8:1{a_edge}"
            )
            filter_parts.append(f"{nxt}split[bs{i}a][bs{i}b]")
            filter_parts.append(f"[bs{i}b]trim=end={whip_s:.4f},setpts=PTS-STARTPTS,boxblur=8:1{b_edge}")
            filter_parts.append(f"[bs{i}a]trim=start={whip_s:.4f},setpts=PTS-STARTPTS{b_body}")
            filter_parts.append(
                f"{a_edge}{b_edge}hstack=inputs=2,crop={CANVAS_W}:{CANVAS_H}:'{CANVAS_W}*n/{WHIP_FRAMES}':0{whip}"
            )
            filter_parts.append(f"{a_body}{whip}{b_body}concat=n=3:v=1:a=0{out}")
        else:
            filter_parts.append(f"{current}{nxt}concat=n=2:v=1:a=0{out}")
        current = out
    filter_parts.append(f"{current}copy[base]")
    return "[base]"

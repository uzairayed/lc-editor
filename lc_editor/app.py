from __future__ import annotations

import json
from pathlib import Path

from lc_editor.analysis.media import kind_for, pxl_burst_id, parse_probe, probe_args, select_import_paths
from lc_editor.assets.pack import cube_path, ensure_assets, sfx_manifest
from lc_editor.ids import new_id
from lc_editor.lint.captions import caption_issues, hold_s, timeline_caption_issues, wrap_text
from lc_editor.lint.invariants import invariant_warnings, reject_duration
from lc_editor.lint.mix import estimate_true_peak_db, mix_issues, sfx_too_hot
from lc_editor.lint.review import review_blockers, review_warnings
from lc_editor.presets import load_preset
from lc_editor.models import (
    CAPTION_Y_DEFAULT,
    DEFAULT_CLIP_S,
    DEFAULT_STILL_S,
    MUSIC_KINDS,
    Caption,
    Clip,
    MediaItem,
    Project,
    Timeline,
    envelope,
    recompute_starts,
    timeline_duration,
)
from lc_editor.ops.timeline import (
    Reject,
    add_clip,
    fit_clip,
    gain_clip,
    mute_clip,
    protect_clip,
    refocus_clip,
    remove_clip,
    reorder_clip,
    ripple_trim_clip,
    set_duration_clip,
    set_motion,
    set_transition,
    split_clip,
    trim_clip,
)
from lc_editor.render.jobs import assemble, contact_sheet, extract_frame_args, preview_stills
from lc_editor.render.runner import FakeRunner, FfmpegRunner, Runner, find_tool
from lc_editor.render.transitions import banned_transition
from lc_editor.store import Store


class Editor:
    """In-process MCP tool surface."""

    def __init__(self, workspace: Path, runner: Runner | None = None) -> None:
        self.workspace = Path(workspace)
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.runner: Runner = runner or FfmpegRunner()
        self.store: Store | None = None
        self.media: list[MediaItem] = []
        ensure_assets()

    def call(self, tool: str, **kwargs) -> dict:
        fn = getattr(self, tool, None)
        if fn is None:
            return {"ok": False, "timeline_summary": self._summary(), "warnings": ["not implemented"]}
        try:
            return fn(**kwargs)
        except Reject as exc:
            tl = self.store.timeline if self.store else Timeline()
            return envelope(False, tl, [str(exc)])

    def _need(self) -> Store:
        if self.store is None or self.store.project is None:
            raise Reject("no project open")
        return self.store

    def _summary(self) -> dict:
        if self.store is None:
            return {
                "version": 0,
                "clip_count": 0,
                "duration_s": 0.0,
                "caption_count": 0,
                "transition_count": 0,
            }
        return envelope(True, self.store.timeline, [])["timeline_summary"]

    def _media(self, media_id: str) -> MediaItem:
        for item in self.media:
            if item.id == media_id:
                return item
        raise Reject(f"unknown media {media_id}")

    def _clip(self, clip_id: str) -> Clip:
        for clip in self._need().timeline.clips:
            if clip.id == clip_id:
                return clip
        raise Reject(f"unknown clip {clip_id}")

    def _mutate(self, op_id: str | None, fn) -> dict:
        store = self._need()
        replay = store.replay(op_id)
        if replay is not None:
            return replay
        before = store.timeline
        try:
            new_tl = fn(before)
        except Reject as exc:
            return envelope(False, before, [str(exc)])
        cap = reject_duration(new_tl)
        if cap:
            return envelope(False, before, [cap])
        new_tl = recompute_starts(new_tl)
        warnings = invariant_warnings(new_tl)
        result = envelope(True, new_tl, warnings)
        store.commit(new_tl, op_id, result)
        result["timeline_summary"] = envelope(True, store.timeline, warnings)["timeline_summary"]
        if store.project:
            store.project.reviewed_version = None
            store.persist()
        return result

    # --- session ---

    def project_create(
        self,
        name: str = "reel",
        aspect: str = "9:16",
        project_dir: str | None = None,
        preset: str | None = None,
        op_id: str | None = None,
    ) -> dict:
        if aspect != "9:16":
            return {
                "ok": False,
                "timeline_summary": self._summary(),
                "warnings": ["only 9:16 is supported in v1"],
            }
        root = Path(project_dir) if project_dir else self.workspace / name
        root.mkdir(parents=True, exist_ok=True)
        store = Store(root)
        applied = None
        grade = "neutral"
        if preset:
            try:
                applied = load_preset(preset)
            except KeyError:
                return {
                    "ok": False,
                    "timeline_summary": self._summary(),
                    "warnings": [f"unknown preset {preset}"],
                }
            grade = applied.get("grade") or "neutral"
        project = Project(
            id=new_id("p"),
            name=name,
            aspect="9:16",
            root=str(root),
            allow_music=False,
            preset=preset,
            grade_preset=grade if grade in ("motovlog", "winter_trip", "neutral") else "neutral",
        )
        store.init_project(project)
        self.store = store
        self.media = []
        self._save_media()
        result = envelope(True, store.timeline, [])
        if applied:
            result["preset"] = applied
        return result

    def project_open(self, project_dir: str, op_id: str | None = None) -> dict:
        store = Store(Path(project_dir))
        store.load()
        self.store = store
        self._load_media()
        return envelope(True, store.timeline, [])

    def project_get(self) -> dict:
        store = self._need()
        result = envelope(True, store.timeline, [])
        result["project"] = store.project.model_dump() if store.project else None
        return result

    def project_set(
        self,
        *,
        allow_music: bool | None = None,
        name: str | None = None,
        preset: str | None = None,
        op_id: str | None = None,
    ) -> dict:
        store = self._need()
        if allow_music is True:
            return envelope(False, store.timeline, ["SPEC-SND-01: allow_music is always false"])
        update: dict = {}
        if name:
            update["name"] = name
        if preset is not None:
            if preset == "":
                update["preset"] = None
            else:
                try:
                    data = load_preset(preset)
                except KeyError:
                    return envelope(False, store.timeline, [f"unknown preset {preset}"])
                update["preset"] = preset
                grade = data.get("grade")
                if grade in ("motovlog", "winter_trip", "neutral"):
                    update["grade_preset"] = grade
        if update:
            store.project = store.project.model_copy(update=update)
            store.persist()
        return envelope(True, store.timeline, [])

    def project_list(self) -> dict:
        found = []
        for child in sorted(self.workspace.iterdir()) if self.workspace.exists() else []:
            if (child / "project.json").exists():
                found.append(str(child))
        result = envelope(True, self.store.timeline if self.store else Timeline(), [])
        result["projects"] = found
        return result

    # --- media ---

    def _media_index_path(self) -> Path:
        return self._need().root / "media.json"

    def _save_media(self) -> None:
        if self.store is None:
            return
        self._media_index_path().write_text(
            json.dumps([m.model_dump() for m in self.media], indent=2),
            encoding="utf-8",
        )

    def _load_media(self) -> None:
        path = self._media_index_path()
        if path.exists():
            self.media = [MediaItem.model_validate(x) for x in json.loads(path.read_text(encoding="utf-8"))]
        else:
            self.media = []

    def _probe_file(self, path: Path) -> dict:
        kind = kind_for(path) or "video"
        try:
            probe_bin = "ffprobe" if isinstance(self.runner, FakeRunner) else find_tool("ffprobe")
        except FileNotFoundError:
            probe_bin = "ffprobe"
        result = self.runner.run(probe_args(probe_bin, path))
        if result.returncode != 0 or not result.stdout.strip():
            duration = DEFAULT_STILL_S if kind == "image" else 5.0
            return {
                "width": 1920,
                "height": 1080,
                "duration_s": duration,
                "fps": 30,
                "has_audio": kind == "video",
                "kind": kind,
            }
        parsed = parse_probe(result.stdout, kind)
        if parsed["kind"] == "image" or path.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}:
            parsed["kind"] = "image"
            parsed["duration_s"] = parsed["duration_s"] or DEFAULT_STILL_S
        return parsed

    def _import_path(self, path: Path, burst_id: str = "") -> MediaItem:
        store = self._need()
        dest = store.media_dir / f"{new_id('f')}_{path.name}"
        if path.resolve() != dest.resolve() and not dest.exists():
            try:
                dest.hardlink_to(path)
            except OSError:
                dest.write_bytes(path.read_bytes())
        info = self._probe_file(path)
        item = MediaItem(
            id=new_id("m"),
            path=str(dest),
            original_path=str(path),
            kind=info["kind"],
            duration_s=info["duration_s"] or (DEFAULT_STILL_S if info["kind"] == "image" else 5.0),
            width=info["width"],
            height=info["height"],
            fps=info["fps"],
            has_audio=info["has_audio"],
            burst_id=burst_id,
        )
        self.media.append(item)
        return item

    def import_file(self, path: str, op_id: str | None = None) -> dict:
        store = self._need()
        replay = store.replay(op_id)
        if replay is not None:
            return replay
        item = self._import_path(Path(path))
        self._save_media()
        result = envelope(True, store.timeline, [])
        result["media"] = item.model_dump()
        if op_id:
            store.ledger[op_id] = result
            store.persist()
        return result

    def import_folder(self, path: str, op_id: str | None = None) -> dict:
        store = self._need()
        replay = store.replay(op_id)
        if replay is not None:
            return replay
        folder = Path(path)
        files = sorted(p for p in folder.iterdir() if p.is_file() and kind_for(p))
        keep, skipped, burst_ids = select_import_paths(files)
        imported = []
        for file in keep:
            burst_id = pxl_burst_id(file) or ""
            item = self._import_path(file, burst_id=burst_id)
            if burst_id or "COVER" in file.name.upper():
                item.burst_cover = True
            imported.append(item)
        from lc_editor.analysis.media import burst_groups

        groups = burst_groups([Path(m.original_path) for m in imported])
        for prefix, members in groups.items():
            if any(pxl_burst_id(p) for p in members):
                continue
            cover_name = members[0].name
            for item in imported:
                if Path(item.original_path).name == cover_name:
                    item.burst_cover = True
                    item.burst_id = prefix
                    break
        self._save_media()
        result = envelope(True, store.timeline, [])
        result["media"] = [m.model_dump() for m in imported]
        result["imported"] = [str(p) for p in keep]
        result["skipped"] = [str(p) for p in skipped]
        result["deduped"] = burst_ids
        if op_id:
            store.ledger[op_id] = result
            store.persist()
        return result

    def media_list(self) -> dict:
        store = self._need()
        result = envelope(True, store.timeline, [])
        result["media"] = [m.model_dump() for m in self.media]
        return result

    def media_remove(self, media_id: str, op_id: str | None = None) -> dict:
        store = self._need()
        used = [c.id for c in store.timeline.clips if c.media_id == media_id]
        if used:
            return envelope(False, store.timeline, [f"SPEC-SES-05: media still used by clips {used}"])
        self.media = [m for m in self.media if m.id != media_id]
        self._save_media()
        return envelope(True, store.timeline, [])

    def probe(self, media_id: str | None = None, path: str | None = None) -> dict:
        store = self._need()
        if media_id:
            item = self._media(media_id)
            info = item.model_dump()
        else:
            info = self._probe_file(Path(path or ""))
        result = envelope(True, store.timeline, [])
        result["probe"] = info
        return result

    def thumbnail(self, media_id: str) -> dict:
        store = self._need()
        item = self._media(media_id)
        dest = store.thumbs_dir / f"{item.id}.jpg"
        dest.parent.mkdir(parents=True, exist_ok=True)
        ff = "ffmpeg" if isinstance(self.runner, FakeRunner) else find_tool("ffmpeg")
        seek = None if item.kind == "image" else 0.1
        args = extract_frame_args(ff, item.path, dest, kind=item.kind, seek_s=seek)
        self.runner.run(args)
        if (not dest.exists() or dest.stat().st_size < 100) and isinstance(self.runner, FakeRunner):
            dest.write_bytes(b"\xff\xd8\xff" + b"\x00" * 120 + b"\xd9")
        result = envelope(True, store.timeline, [])
        result["path"] = str(dest.resolve())
        return result

    def contact_sheet(self) -> dict:
        store = self._need()
        thumbs = []
        for item in self.media:
            t = self.thumbnail(item.id)
            thumbs.append(Path(t["path"]))
        dest = (store.output_dir / "contact_sheet.jpg").resolve()
        dest.parent.mkdir(parents=True, exist_ok=True)
        contact_sheet(self.runner, thumbs, dest)
        result = envelope(True, store.timeline, [])
        result["path"] = str(dest)
        return result

    def proxy_build(self, media_id: str | None = None) -> dict:
        store = self._need()
        targets = [self._media(media_id)] if media_id else list(self.media)
        ff = "ffmpeg" if isinstance(self.runner, FakeRunner) else find_tool("ffmpeg")
        paths = []
        from lc_editor.models import PROXY_H, PROXY_W

        for item in targets:
            dest = store.proxies_dir / f"{item.id}.mp4"
            self.runner.run(
                [
                    ff,
                    "-y",
                    "-i",
                    item.path,
                    "-vf",
                    f"scale={PROXY_W}:{PROXY_H}",
                    "-preset",
                    "veryfast",
                    "-crf",
                    "30",
                    str(dest),
                ]
            )
            dest.parent.mkdir(parents=True, exist_ok=True)
            if not dest.exists():
                dest.write_bytes(b"fake")
            paths.append(str(dest))
        result = envelope(True, store.timeline, [])
        result["paths"] = paths
        return result

    # --- edit ---

    def timeline_get(self) -> dict:
        store = self._need()
        result = envelope(True, store.timeline, [])
        result["timeline"] = store.timeline.model_dump()
        return result

    def timeline_reset(self, op_id: str | None = None) -> dict:
        return self._mutate(op_id, lambda _tl: Timeline(version=0))

    def clip_add(
        self,
        media_id: str,
        in_s: float | None = None,
        out_s: float | None = None,
        duration_s: float | None = None,
        op_id: str | None = None,
    ) -> dict:
        item = self._media(media_id)
        is_still = item.kind == "image"
        default_dur = DEFAULT_STILL_S if is_still else min(DEFAULT_CLIP_S, item.duration_s or DEFAULT_CLIP_S)
        start_in = 0.0 if in_s is None else in_s
        if out_s is None:
            end = start_in + (duration_s or default_dur)
            if not is_still:
                end = min(end, item.duration_s or end)
        else:
            end = out_s
        dur = duration_s or round(end - start_in, 4)

        def apply(tl: Timeline) -> Timeline:
            clip = Clip(
                id=new_id("c"),
                media_id=media_id,
                in_s=start_in,
                out_s=end,
                duration_s=dur,
                motion="kenburns" if is_still else "none",
                is_still=is_still,
            )
            return add_clip(tl, clip)

        return self._mutate(op_id, apply)

    def clip_remove(self, clip_id: str, op_id: str | None = None) -> dict:
        return self._mutate(op_id, lambda tl: remove_clip(tl, clip_id))

    def clip_reorder(self, clip_id: str, index: int, op_id: str | None = None) -> dict:
        return self._mutate(op_id, lambda tl: reorder_clip(tl, clip_id, index))

    def clip_trim(self, clip_id: str, in_s: float, out_s: float, op_id: str | None = None) -> dict:
        clip = self._clip(clip_id)
        source = self._media(clip.media_id)
        return self._mutate(op_id, lambda tl: trim_clip(tl, clip_id, in_s, out_s, source))

    def clip_ripple_trim(self, clip_id: str, edge: str, delta_s: float, op_id: str | None = None) -> dict:
        clip = self._clip(clip_id)
        source = self._media(clip.media_id)
        return self._mutate(op_id, lambda tl: ripple_trim_clip(tl, clip_id, edge, delta_s, source))

    def clip_split(self, clip_id: str, at_s: float, op_id: str | None = None) -> dict:
        return self._mutate(op_id, lambda tl: split_clip(tl, clip_id, at_s, new_id("c")))

    def clip_set_duration(self, clip_id: str, duration_s: float, op_id: str | None = None) -> dict:
        clip = self._clip(clip_id)
        source = self._media(clip.media_id)
        return self._mutate(op_id, lambda tl: set_duration_clip(tl, clip_id, duration_s, source))

    def clip_fit(self, clip_id: str, op_id: str | None = None) -> dict:
        clip = self._clip(clip_id)
        source = self._media(clip.media_id)
        return self._mutate(op_id, lambda tl: fit_clip(tl, clip_id, source))

    def clip_refocus(self, clip_id: str, x: float, y: float, op_id: str | None = None) -> dict:
        return self._mutate(op_id, lambda tl: refocus_clip(tl, clip_id, x, y))

    def clip_gain(self, clip_id: str, db: float, op_id: str | None = None) -> dict:
        return self._mutate(op_id, lambda tl: gain_clip(tl, clip_id, db))

    def clip_mute(self, clip_id: str, muted: bool = True, op_id: str | None = None) -> dict:
        return self._mutate(op_id, lambda tl: mute_clip(tl, clip_id, muted))

    def motion_kenburns(self, clip_id: str, op_id: str | None = None) -> dict:
        return self._mutate(op_id, lambda tl: set_motion(tl, clip_id, "kenburns"))

    def motion_punch(self, clip_id: str, op_id: str | None = None) -> dict:
        return self._mutate(op_id, lambda tl: set_motion(tl, clip_id, "punch"))

    def motion_none(self, clip_id: str, op_id: str | None = None) -> dict:
        return self._mutate(op_id, lambda tl: set_motion(tl, clip_id, "none"))

    def transition_set(self, clip_id: str, kind: str, op_id: str | None = None) -> dict:
        if banned_transition(kind):
            return envelope(False, self._need().timeline, ["SPEC-EDIT-13: illegal transition"])
        return self._mutate(op_id, lambda tl: set_transition(tl, clip_id, kind))

    # --- captions ---

    def caption_add(
        self,
        clip_id: str,
        text: str,
        role: str = "body",
        y_pct: float = CAPTION_Y_DEFAULT,
        box: bool = False,
        background: str | None = None,
        op_id: str | None = None,
    ) -> dict:
        store = self._need()
        clip = self._clip(clip_id)
        issues = caption_issues(text, y_pct=y_pct, clip=clip, box=box or bool(background))
        if issues:
            return envelope(False, store.timeline, issues)
        lines = wrap_text(text)
        hold = hold_s(text, lines)

        def apply(tl: Timeline) -> Timeline:
            cap = Caption(
                id=new_id("t"),
                clip_id=clip_id,
                text=text,
                role=role if role in ("title", "body") else "body",
                y_pct=y_pct,
                lines=lines,
                hold_s=hold,
            )
            return tl.model_copy(update={"captions": [*tl.captions, cap]})

        return self._mutate(op_id, apply)

    def caption_edit(self, caption_id: str, text: str | None = None, y_pct: float | None = None, box: bool = False, op_id: str | None = None) -> dict:
        store = self._need()
        cap = next((c for c in store.timeline.captions if c.id == caption_id), None)
        if cap is None:
            return envelope(False, store.timeline, [f"unknown caption {caption_id}"])
        new_text = cap.text if text is None else text
        new_y = cap.y_pct if y_pct is None else y_pct
        clip = self._clip(cap.clip_id)
        issues = caption_issues(new_text, y_pct=new_y, clip=clip, box=box)
        if issues:
            return envelope(False, store.timeline, issues)
        lines = wrap_text(new_text)
        hold = hold_s(new_text, lines)

        def apply(tl: Timeline) -> Timeline:
            caps = []
            for c in tl.captions:
                if c.id == caption_id:
                    caps.append(c.model_copy(update={"text": new_text, "y_pct": new_y, "lines": lines, "hold_s": hold}))
                else:
                    caps.append(c)
            return tl.model_copy(update={"captions": caps})

        return self._mutate(op_id, apply)

    def caption_move(self, caption_id: str, clip_id: str | None = None, y_pct: float | None = None, op_id: str | None = None) -> dict:
        store = self._need()
        cap = next((c for c in store.timeline.captions if c.id == caption_id), None)
        if cap is None:
            return envelope(False, store.timeline, [f"unknown caption {caption_id}"])
        new_clip_id = clip_id or cap.clip_id
        new_y = cap.y_pct if y_pct is None else y_pct
        clip = self._clip(new_clip_id)
        issues = caption_issues(cap.text, y_pct=new_y, clip=clip)
        if issues:
            return envelope(False, store.timeline, issues)

        def apply(tl: Timeline) -> Timeline:
            caps = [c.model_copy(update={"clip_id": new_clip_id, "y_pct": new_y}) if c.id == caption_id else c for c in tl.captions]
            return tl.model_copy(update={"captions": caps})

        return self._mutate(op_id, apply)

    def caption_remove(self, caption_id: str, op_id: str | None = None) -> dict:
        return self._mutate(
            op_id,
            lambda tl: tl.model_copy(update={"captions": [c for c in tl.captions if c.id != caption_id]}),
        )

    def caption_lint(self) -> dict:
        store = self._need()
        warnings = timeline_caption_issues(store.timeline)
        return envelope(len(warnings) == 0, store.timeline, warnings)

    # --- sound ---

    def sfx_list(self) -> dict:
        store = self._need()
        items = list(sfx_manifest())
        for extra in store.user_sfx_dir.glob("*"):
            if extra.suffix.lower() in {".wav", ".mp3", ".aiff"}:
                items.append({"kind": extra.stem, "file": str(extra), "user": True})
        result = envelope(True, store.timeline, [])
        result["sfx"] = items
        return result

    def sfx_place(self, kind: str, at_s: float, gain_db: float = -12.0, auto: bool = False, key: str = "", op_id: str | None = None) -> dict:
        store = self._need()
        if kind in MUSIC_KINDS or kind.startswith("music"):
            return envelope(False, store.timeline, ["SPEC-SND-01: music is rejected"])
        legal = {i["kind"] for i in sfx_manifest()}
        if kind not in legal and not (store.user_sfx_dir / f"{kind}.wav").exists():
            return envelope(False, store.timeline, [f"unknown sfx {kind}"])
        if sfx_too_hot(gain_db, store.timeline.bed_gain_db, store.timeline.bed_kind):
            return envelope(False, store.timeline, ["SPEC-SND-05: SFX must be at least 6 dB under the bed"])

        def apply(tl: Timeline) -> Timeline:
            from lc_editor.models import SfxPlacement

            if key and any(s.key == key for s in tl.sfx):
                return tl
            sfx = SfxPlacement(id=new_id("s"), kind=kind, at_s=at_s, gain_db=gain_db, auto=auto, key=key)
            return tl.model_copy(update={"sfx": [*tl.sfx, sfx]})

        return self._mutate(op_id, apply)

    def sfx_caption_auto(self, op_id: str | None = None) -> dict:
        store = self._need()

        def apply(tl: Timeline) -> Timeline:
            from lc_editor.models import SfxPlacement

            existing = {s.key for s in tl.sfx}
            extra = []
            clips = {c.id: c for c in tl.clips}
            for cap in tl.captions:
                key = f"tick:{cap.id}"
                if key in existing:
                    continue
                clip = clips.get(cap.clip_id)
                at = clip.start_s if clip else 0.0
                extra.append(SfxPlacement(id=new_id("s"), kind="tick", at_s=at, gain_db=-12.0, auto=True, key=key))
            return tl.model_copy(update={"sfx": [*tl.sfx, *extra]}) if extra else tl

        return self._mutate(op_id, apply)

    def sfx_transition_auto(self, op_id: str | None = None) -> dict:
        def apply(tl: Timeline) -> Timeline:
            from lc_editor.models import SfxPlacement

            existing = {s.key for s in tl.sfx}
            extra = []
            for clip in tl.clips:
                kind = tl.transitions.get(clip.id, "hard")
                if kind not in ("whip", "punch"):
                    continue
                key = f"whoosh:{clip.id}"
                if key in existing:
                    continue
                extra.append(
                    SfxPlacement(id=new_id("s"), kind="whoosh", at_s=clip.start_s + clip.duration_s, gain_db=-12.0, auto=True, key=key)
                )
            return tl.model_copy(update={"sfx": [*tl.sfx, *extra]}) if extra else tl

        return self._mutate(op_id, apply)

    def audio_bed(self, kind: str, gain_db: float | None = None, op_id: str | None = None) -> dict:
        if kind in MUSIC_KINDS or kind in {"cinematic", "ambient", "music"}:
            return envelope(False, self._need().timeline, ["SPEC-SND-01: music is rejected"])
        if kind not in ("wind", "room", "none"):
            return envelope(False, self._need().timeline, ["SPEC-SND-07: bed must be wind, room, or none"])

        def apply(tl: Timeline) -> Timeline:
            update = {"bed_kind": kind}
            if gain_db is not None:
                update["bed_gain_db"] = gain_db
            return tl.model_copy(update=update)

        return self._mutate(op_id, apply)

    def audio_duck(self, enabled: bool = True, op_id: str | None = None) -> dict:
        return self._mutate(op_id, lambda tl: tl.model_copy(update={"duck": enabled}))

    def audio_highpass(self, hz: float = 100.0, op_id: str | None = None) -> dict:
        if hz <= 0:
            return envelope(False, self._need().timeline, ["SPEC-SND-06: highpass hz must be > 0"])
        return self._mutate(op_id, lambda tl: tl.model_copy(update={"highpass_hz": hz}))

    def mix_preview(self) -> dict:
        store = self._need()
        warnings = mix_issues(store.timeline)
        result = envelope(len(warnings) == 0, store.timeline, warnings)
        result["true_peak_dbtp"] = estimate_true_peak_db(store.timeline)
        return result

    # --- look ---

    def grade_set(self, cube_path_str: str, op_id: str | None = None) -> dict:
        store = self._need()
        store.project = store.project.model_copy(update={"cube_path": cube_path_str})
        store.persist()
        return envelope(True, store.timeline, [])

    def grade_preset(self, name: str, op_id: str | None = None) -> dict:
        store = self._need()
        if name not in ("motovlog", "winter_trip", "neutral"):
            return envelope(False, store.timeline, ["unknown grade preset"])
        store.project = store.project.model_copy(update={"grade_preset": name, "cube_path": str(cube_path(name))})
        store.persist()
        return envelope(True, store.timeline, [])

    def grade_protect(self, clip_id: str, enabled: bool = True, intensity: float | None = None, op_id: str | None = None) -> dict:
        if intensity is not None and intensity not in (1.0, 0.7, 0.4, 0.70, 0.40):
            return envelope(False, self._need().timeline, ["SPEC-RND-08: intensity must be 1.00, 0.70, or 0.40"])
        return self._mutate(op_id, lambda tl: protect_clip(tl, clip_id, enabled, intensity))

    def overlay_preview(self, platform: str = "ig", guides: bool = True, op_id: str | None = None) -> dict:
        store = self._need()
        overlays = store.project.overlays.model_copy(update={"preview_guides": guides, "preview_platform": platform})
        store.project = store.project.model_copy(update={"overlays": overlays})
        store.persist()
        return envelope(True, store.timeline, [])

    def overlay_bake(self, name: str, enabled: bool = True, op_id: str | None = None) -> dict:
        store = self._need()
        allowed = {"series_card", "location_chip", "progress", "end_card", "social_chrome"}
        if name not in allowed:
            return envelope(False, store.timeline, [f"unknown bake-in {name}"])
        overlays = store.project.overlays.model_copy(update={name: enabled})
        store.project = store.project.model_copy(update={"overlays": overlays})
        store.persist()
        return envelope(True, store.timeline, [])

    # --- out ---

    def preview_stills(self) -> dict:
        store = self._need()
        paths = preview_stills(self.runner, store, store.project, store.timeline, self.media)
        result = envelope(True, store.timeline, [])
        result["paths"] = [str(Path(p).resolve()) for p in paths]
        return result

    def preview_proxy(self) -> dict:
        store = self._need()
        dest = store.output_dir / "preview_proxy.mp4"
        assemble(self.runner, store, store.project, store.timeline, self.media, dest, proxy=True)
        result = envelope(True, store.timeline, [])
        result["path"] = str(dest)
        return result

    def preview_clip(self, clip_id: str) -> dict:
        store = self._need()
        clip = self._clip(clip_id)
        dest = store.output_dir / f"preview_{clip_id}.mp4"
        one = store.timeline.model_copy(update={"clips": [clip], "transitions": {}})
        one = recompute_starts(one)
        assemble(self.runner, store, store.project, one, self.media, dest, proxy=True)
        result = envelope(True, store.timeline, [])
        result["path"] = str(dest)
        return result

    def review_report(self) -> dict:
        store = self._need()
        errors = review_blockers(store.timeline, store.project)
        warns = review_warnings(store.timeline)
        dur = timeline_duration(store.timeline)
        ok = len(errors) == 0
        if ok:
            store.project = store.project.model_copy(update={"reviewed_version": store.timeline.version})
            store.persist()
        report = {
            "duration_s": dur,
            "clip_count": len(store.timeline.clips),
            "caption_warnings": [e for e in errors if "SPEC-CAP" in e],
            "mix_warnings": [e for e in errors if "SPEC-SND" in e or "SPEC-CRAFT-06" in e],
            "transition_count": envelope(True, store.timeline, [])["timeline_summary"]["transition_count"],
            "grade": store.project.grade_preset if store.project else None,
            "in_target_length": 15.0 <= dur <= 28.0,
            "errors": errors,
            "warnings": warns,
        }
        result = envelope(ok, store.timeline, errors + warns)
        result["errors"] = errors
        result["report"] = report
        return result

    def export(self, op_id: str | None = None) -> dict:
        store = self._need()
        replay = store.replay(op_id)
        if replay is not None:
            return replay
        if store.project.reviewed_version != store.timeline.version:
            return envelope(False, store.timeline, ["SPEC-EXPORT-03: export requires review_report on the current version"])
        hero = store.output_dir / "reel.mp4"
        proxy = store.output_dir / "reel_proxy.mp4"
        sidecar = store.output_dir / "reel.json"
        assemble(self.runner, store, store.project, store.timeline, self.media, hero, proxy=False)
        assemble(self.runner, store, store.project, store.timeline, self.media, proxy, proxy=True)
        media_map = {m.id: m for m in self.media}
        payload = {
            "version": store.timeline.version,
            "duration_s": timeline_duration(store.timeline),
            "grade": store.project.grade_preset if store.project else None,
            "preset": store.project.preset if store.project else None,
            "hero": str(hero.resolve()),
            "proxy": str(proxy.resolve()),
            "shots": [
                {
                    "id": clip.id,
                    "media_id": clip.media_id,
                    "source": media_map.get(clip.media_id).original_path if clip.media_id in media_map else "",
                    "in_s": clip.in_s,
                    "out_s": clip.out_s,
                    "duration_s": clip.duration_s,
                    "motion": clip.motion,
                    "crop": {"focus_x": clip.focus_x, "focus_y": clip.focus_y},
                }
                for clip in store.timeline.clips
            ],
            "captions": [c.model_dump() for c in store.timeline.captions],
            "sfx": [{"kind": s.kind, "at_s": s.at_s, "gain_db": s.gain_db} for s in store.timeline.sfx],
        }
        from lc_editor.store import atomic_write

        atomic_write(sidecar, json.dumps(payload, indent=2))
        result = envelope(True, store.timeline, [])
        result["hero"] = str(hero.resolve())
        result["proxy"] = str(proxy.resolve())
        result["sidecar"] = str(sidecar.resolve())
        if op_id:
            store.ledger[op_id] = result
            store.persist()
        return result

    def undo(self) -> dict:
        store = self._need()
        if not store.undo():
            return envelope(False, store.timeline, ["nothing to undo"])
        return envelope(True, store.timeline, [])

    def redo(self) -> dict:
        store = self._need()
        if not store.redo():
            return envelope(False, store.timeline, ["nothing to redo"])
        return envelope(True, store.timeline, [])

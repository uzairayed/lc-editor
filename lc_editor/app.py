from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field

from lc_editor.analysis.detect import detect_box
from lc_editor.analysis.manifest import Shot, load_manifest, manifest_path, shot_id, write_manifest
from lc_editor.analysis.media import (
    captured_at_sort_key,
    kind_for,
    media_index_summary,
    normalize_role,
    normalize_shoot_day,
    parse_probe,
    probe_args,
    public_media,
    pxl_burst_id,
    quality_import_warning,
    quality_soft_warnings,
    read_exif_tags,
    resolve_captured_at,
    roles_equal,
    select_import_paths,
    shoot_days_equal,
)
from lc_editor.analysis.rank import (
    PROCESS_STORY_ORDER,
    ROLES,
    contradictory_filters,
    filter_shots,
    rank_shots,
    score_shot,
    shot_has_any_understand_tag,
    shot_has_understand_role,
    sort_shots,
)
from lc_editor.analysis.shots import (
    analysis_pass_args,
    keyframe_sharpness,
    metrics_for_span,
    parse_astats,
    parse_scdet,
    parse_signalstats,
    segment_shots,
)
from lc_editor.analysis.adaptive import (
    DEFAULT_SELECTION,
    allocate_shared_budget,
    clamp_shared_budget,
    media_duration_s,
    normalize_selection,
    select_adaptive_shots,
    understand_cost_metrics,
)
from lc_editor.analysis.embedder import embedder_status, optional_embedder
from lc_editor.analysis.spatial import (
    annotate_span_spatial,
    clamp_spatial_budget,
    pick_hint_for_span,
    select_spatial_targets,
    spatial_cover_warnings,
    spatial_refocus_warning,
    spatial_windows,
)
from lc_editor.analysis.highlights import (
    clamp_target_s,
    normalize_style,
    suggest_highlight_sheets,
)
from lc_editor.analysis.labels import (
    LABEL_UNDO_MAX,
    build_label_queue,
    collect_conflicts,
    confirmed_shot_roles_map,
    readiness_payload,
    resolve_labels,
)
from lc_editor.analysis.provenance import (
    FOLDER_HINT_CONFIDENCE,
    card_coverage,
    cluster_shoot_days,
    confirmed_roles_map,
    day_for_media,
    hints_from_path,
    is_carded,
    propose_card,
)
from lc_editor.analysis.understand import (
    DEFAULT_REFINE_BUDGET,
    apply_understand_tags,
    build_understand_timeline,
    card_from_shot,
    cards_from_tagged_shots,
    clamp_budget,
    load_understand_cache,
    parent_shot_for_span,
    refine_windows,
    resolve_understand_roles,
    understand_path,
    write_understand_cache,
)
from lc_editor.assets.pack import cube_path, ensure_assets, sfx_manifest
from lc_editor.assets.user_sfx import (
    attribution_path,
    find_user_sfx,
    import_user_sfx_file,
    import_user_sfx_pack,
    list_user_sfx_items,
)
from lc_editor.ids import new_id
from lc_editor.fonts import FONT_ALIAS_HELP, normalize_font
from lc_editor.lint.captions import (
    caption_issues,
    card_report,
    density_warnings,
    hold_s,
    style_warnings,
    suggest_darker_y,
    timeline_caption_issues,
    timeline_caption_warnings,
    wrap_text,
    write_phone_proof,
)
from lc_editor.lint.invariants import invariant_warnings, reject_duration
from lc_editor.lint.mix import mix_issues, mix_preview_payload, sfx_too_hot
from lc_editor.lint.review import (
    resolve_density_allow,
    review_blockers,
    review_warnings,
    video_duration_floor_errors,
    video_duration_floor_warnings,
    video_floor_reject,
    zoom_suggestions,
)
from lc_editor.presets import load_preset, project_fields_from_preset
from lc_editor.analysis.beats import analyze_beats
from lc_editor.migrate import sync_caption_layers
from lc_editor.models import (
    CAPTION_Y_DEFAULT,
    DEFAULT_STILL_S,
    FPS,
    DURATION_CAP_MAX_S,
    DURATION_CAP_S,
    DURATION_SOFT_MIN_S,
    MIN_VIDEO_DURATION_S,
    SHOT_ACK_MIN_S,
    resolved_duration_cap_s,
    resolved_duration_soft_max_s,
    resolved_min_video_duration_s,
    SOURCE_PROXY_H,
    SOURCE_PROXY_W,
    MUSIC_KINDS,
    Cc0SfxKind,
    AdjustmentLayer,
    BeatGrid,
    CamPip,
    Caption,
    CaptionWord,
    Clip,
    ClipBlur,
    EffectInstance,
    Keyframe,
    LayerItem,
    LayoutPane,
    CardSource,
    MediaCard,
    MediaItem,
    QUEUE_FILTERS,
    ShotCard,
    MusicTrack,
    Project,
    TextStyle,
    Timeline,
    Transform,
    envelope,
    is_card_style,
    is_spoken_style,
    recompute_starts,
    resolve_canvas,
    timeline_duration,
)
from lc_editor.ops.blurs import (
    add_blur,
    list_blurs,
    remove_blur,
    update_blur,
    validate_blur_box,
    validate_blur_feather,
    validate_blur_kind,
    validate_blur_strength,
)
from lc_editor.ops.layouts import (
    add_layout,
    build_layout_clip,
    clear_layout,
    parse_panes,
    resolve_layout_duration,
    set_layout_pane,
    update_layout,
    validate_layout,
)
from lc_editor.ops.layers import (
    add_effect,
    add_keyframe,
    add_layer,
    remove_effect,
    remove_layer,
    reorder_layer,
    set_transform,
    update_effect,
    update_layer,
)
from lc_editor.ops.music import add_music, remove_music, set_beat_grid, update_music
from lc_editor.ops.sync import apply_beat_sync, propose_beat_sync
from lc_editor.ops.templates import apply_template, list_templates, load_template, save_template
from lc_editor.ops.timeline import (
    Reject,
    add_clip,
    clip_id_for_transition_at,
    fit_clip,
    gain_clip,
    mute_clip,
    protect_clip,
    refocus_clip,
    remove_clip,
    reorder_clip,
    ripple_trim_clip,
    set_audio_xfade,
    set_cam_pip,
    set_clip_fit,
    set_denoise,
    set_duration_clip,
    set_gate,
    set_motion,
    set_speed,
    set_transition,
    set_wrap,
    set_zoom_pair,
    source_hold_warning,
    split_clip,
    trim_clip,
)
from lc_editor.render.captions import expand_contractions
from lc_editor.render.effects import validate_effect
from lc_editor.render.graph import hero_encode_args, hero_encode_record, share_encode_args
from lc_editor.render.jobs import (
    assemble,
    AssembleError,
    contact_sheet,
    ensure_source_proxy,
    extract_frame_args,
    hero_export_lock,
    HeroExportBusy,
    preview_stills,
    source_proxy_hash,
    verify_hero_av,
    working_media,
)
from lc_editor.render.runner import FakeRunner, FfmpegRunner, Runner, find_tool
from lc_editor.render.transitions import banned_transition
from lc_editor.store import Store


def _caption_words(words: list | None) -> list[CaptionWord]:
    if not words:
        return []
    out: list[CaptionWord] = []
    for item in words:
        if isinstance(item, CaptionWord):
            out.append(item)
            continue
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        emphasis = str(item.get("emphasis") or "pop")
        if emphasis not in ("pop", "enlarge", "scream"):
            emphasis = "pop"
        wid = str(item.get("id") or "")
        out.append(
            CaptionWord(
                id=wid,
                text=text,
                start_s=float(item.get("start_s") or 0.0),
                end_s=float(item.get("end_s") or 0.0),
                emphasis=emphasis,  # type: ignore[arg-type]
            )
        )
    return out


class Editor:
    """In-process MCP tool surface."""

    def __init__(self, workspace: Path, runner: Runner | None = None) -> None:
        self.workspace = Path(workspace)
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.runner: Runner = runner or FfmpegRunner()
        self.store: Store | None = None
        self.media: list[MediaItem] = []
        self.shot_cards: dict[str, ShotCard] = {}
        self.label_history: list[dict] = []
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
        cap = reject_duration(new_tl, store.project)
        if cap:
            return envelope(False, before, [cap])
        new_tl = recompute_starts(new_tl)
        new_tl = sync_caption_layers(new_tl)
        warnings = invariant_warnings(new_tl, store.project)
        warnings.extend(video_duration_floor_warnings(new_tl, store.project, self.media))
        warnings.extend(video_duration_floor_errors(new_tl, store.project, self.media))
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
        width: int | None = None,
        height: int | None = None,
        project_dir: str | None = None,
        preset: Annotated[
            Literal["karachi", "process"] | None,
            Field(description="Optional project preset: karachi (series) or process (detailing/wash cards)."),
        ] = None,
        op_id: str | None = None,
    ) -> dict:
        canvas = resolve_canvas(aspect, width, height)
        if canvas is None:
            return {
                "ok": False,
                "timeline_summary": self._summary(),
                "warnings": ["unknown aspect"],
            }
        aspect, canvas_w, canvas_h = canvas
        root = Path(project_dir) if project_dir else self.workspace / name
        root.mkdir(parents=True, exist_ok=True)
        store = Store(root)
        applied = None
        fields: dict = {}
        if preset:
            try:
                applied = load_preset(preset)
            except KeyError:
                return {
                    "ok": False,
                    "timeline_summary": self._summary(),
                    "warnings": [f"unknown preset {preset}"],
                }
            fields = project_fields_from_preset(applied)
        project = Project(
            id=new_id("p"),
            name=name,
            aspect=aspect,
            width=canvas_w,
            height=canvas_h,
            root=str(root),
            allow_music=fields.get("allow_music", False),
            preset=preset,
            grade_preset=fields.get("grade_preset", "neutral"),
            duration_cap_s=fields.get("duration_cap_s", DURATION_CAP_S),
            caption_contrast=fields.get("caption_contrast", "lenient"),
            min_video_duration_s=fields.get("min_video_duration_s", MIN_VIDEO_DURATION_S),
            loudnorm=fields.get("loudnorm", "cinema"),
        )
        store.init_project(project)
        self.store = store
        self.media = []
        self.shot_cards = {}
        self.label_history = []
        self._save_media()
        self._save_shot_cards()
        self._save_label_history()
        result = envelope(True, store.timeline, [])
        if applied:
            result["preset"] = applied
        return result

    def project_open(self, project_dir: str, op_id: str | None = None) -> dict:
        store = Store(Path(project_dir))
        store.load()
        self.store = store
        self._load_media()
        self._load_shot_cards()
        self._load_label_history()
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
        preset: Annotated[
            Literal["karachi", "process", ""] | None,
            Field(description="karachi | process agent defaults; empty string clears preset name."),
        ] = None,
        loudnorm: str | None = None,
        min_video_duration_s: float | None = None,
        duration_cap_s: Annotated[
            float | None,
            Field(description="Hard duration cap in seconds. 0 resets to the default 60.0s."),
        ] = None,
        caption_font: str | None = None,
        caption_contrast: Annotated[
            Literal["strict", "lenient"] | None,
            Field(description="strict hard-fails CAP-06; lenient (default) warns only."),
        ] = None,
        op_id: str | None = None,
    ) -> dict:
        store = self._need()
        update: dict = {}
        if allow_music is not None:
            if allow_music is False and store.timeline.music:
                return envelope(False, store.timeline, ["SPEC-MUS-02: turn off music tracks first"])
            update["allow_music"] = allow_music
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
                update.update(project_fields_from_preset(data))
        if loudnorm is not None:
            if loudnorm not in ("cinema", "speech"):
                return envelope(False, store.timeline, ["loudnorm must be cinema or speech"])
            update["loudnorm"] = loudnorm
        if min_video_duration_s is not None:
            if min_video_duration_s < 0:
                return envelope(False, store.timeline, ["SPEC-EDIT-25: min_video_duration_s must be >= 0"])
            # 0 means "use default 5.0". Omit the argument to leave the stored floor unchanged.
            update["min_video_duration_s"] = (
                MIN_VIDEO_DURATION_S if min_video_duration_s == 0 else float(min_video_duration_s)
            )
            update["reviewed_version"] = None
        if duration_cap_s is not None:
            if duration_cap_s < 0:
                return envelope(False, store.timeline, ["SPEC-EDIT-14: duration_cap_s must be >= 0"])
            if duration_cap_s > DURATION_CAP_MAX_S:
                return envelope(
                    False,
                    store.timeline,
                    [f"SPEC-EDIT-14: duration_cap_s must be <= {DURATION_CAP_MAX_S:.0f}"],
                )
            # 0 means "use default 60.0". Omit the argument to leave the stored cap unchanged.
            update["duration_cap_s"] = DURATION_CAP_S if duration_cap_s == 0 else float(duration_cap_s)
            update["reviewed_version"] = None
        if caption_font is not None:
            if caption_font == "":
                update["caption_font"] = ""
            else:
                resolved = normalize_font(caption_font)
                if not resolved:
                    return envelope(
                        False,
                        store.timeline,
                        [f"unknown font {caption_font}; use {FONT_ALIAS_HELP}"],
                    )
                update["caption_font"] = resolved
        if caption_contrast is not None:
            mode = str(caption_contrast).strip().lower()
            if mode not in {"strict", "lenient"}:
                return envelope(False, store.timeline, ["caption_contrast must be strict or lenient"])
            update["caption_contrast"] = mode
            update["reviewed_version"] = None
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

    def _shot_cards_path(self) -> Path:
        return self._need().shot_cards_path

    def _label_history_path(self) -> Path:
        return self._need().label_history_path

    def _save_shot_cards(self) -> None:
        if self.store is None:
            return
        payload = [card.model_dump() for card in self.shot_cards.values()]
        self._shot_cards_path().write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def _load_shot_cards(self) -> None:
        path = self._shot_cards_path()
        if not path.exists():
            self.shot_cards = {}
            return
        rows = json.loads(path.read_text(encoding="utf-8"))
        cards = rows.get("cards") if isinstance(rows, dict) else rows
        self.shot_cards = {}
        for row in cards or []:
            card = ShotCard.model_validate(row)
            self.shot_cards[card.shot_id] = card

    def _save_label_history(self) -> None:
        if self.store is None:
            return
        self._label_history_path().write_text(
            json.dumps(self.label_history[-LABEL_UNDO_MAX:], indent=2),
            encoding="utf-8",
        )

    def _load_label_history(self) -> None:
        path = self._label_history_path()
        if not path.exists():
            self.label_history = []
            return
        data = json.loads(path.read_text(encoding="utf-8"))
        self.label_history = list(data) if isinstance(data, list) else list(data.get("stack") or [])

    def _label_snapshot(self) -> dict:
        return {
            "media": [item.model_dump() for item in self.media],
            "shot_cards": [card.model_dump() for card in self.shot_cards.values()],
        }

    def _restore_label_snapshot(self, snap: dict) -> None:
        self.media = [MediaItem.model_validate(row) for row in snap.get("media") or []]
        self.shot_cards = {}
        for row in snap.get("shot_cards") or []:
            card = ShotCard.model_validate(row)
            self.shot_cards[card.shot_id] = card
        self._save_media()
        self._save_shot_cards()

    def _push_label_undo(self) -> None:
        self.label_history.append(self._label_snapshot())
        if len(self.label_history) > LABEL_UNDO_MAX:
            self.label_history = self.label_history[-LABEL_UNDO_MAX:]
        self._save_label_history()

    def _shots_by_media(self) -> dict[str, list[Shot]]:
        out: dict[str, list[Shot]] = {}
        for item in self.media:
            path = self._manifest_for(item)
            if path.exists():
                out[item.id] = load_manifest(path)
            else:
                out[item.id] = []
        return out

    def _understand_by_media(self) -> dict[str, list]:
        out: dict[str, list] = {}
        for item in self.media:
            cached = load_understand_cache(self._understand_for(item)) or {}
            out[item.id] = list(cached.get("cards") or [])
        return out

    def _find_shot(self, shot_id: str) -> tuple[MediaItem, Shot]:
        for item in self.media:
            path = self._manifest_for(item)
            if not path.exists():
                continue
            for shot in load_manifest(path):
                if shot.id == shot_id:
                    return item, shot
        raise Reject(f"unknown shot {shot_id}")

    def _load_media(self) -> None:
        path = self._media_index_path()
        if path.exists():
            self.media = [MediaItem.model_validate(x) for x in json.loads(path.read_text(encoding="utf-8"))]
        else:
            self.media = []

    def _attach_capture(self, info: dict, path: Path) -> dict:
        exif = read_exif_tags(path) if path.exists() else {}
        captured_at, source = resolve_captured_at(probe=info, exif=exif, path=path)
        info["captured_at"] = captured_at
        info["captured_at_source"] = source
        return info

    def _probe_file(self, path: Path) -> dict:
        kind = kind_for(path) or "video"
        try:
            probe_bin = "ffprobe" if isinstance(self.runner, FakeRunner) else find_tool("ffprobe")
        except FileNotFoundError:
            probe_bin = "ffprobe"
        result = self.runner.run(probe_args(probe_bin, path))
        if result.returncode != 0 or not result.stdout.strip():
            duration = DEFAULT_STILL_S if kind == "image" else 5.0
            return self._attach_capture(
                {
                    "width": 1920,
                    "height": 1080,
                    "duration_s": duration,
                    "fps": 30,
                    "has_audio": kind == "video",
                    "kind": kind,
                },
                path,
            )
        parsed = parse_probe(result.stdout, kind)
        if parsed["kind"] == "image" or path.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}:
            parsed["kind"] = "image"
            parsed["duration_s"] = parsed["duration_s"] or DEFAULT_STILL_S
        return self._attach_capture(parsed, path)

    def _file_size(self, path: Path) -> int:
        try:
            return int(path.stat().st_size)
        except OSError:
            return 0

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
            captured_at=info.get("captured_at"),
            captured_at_source=info.get("captured_at_source"),
            size_bytes=self._file_size(path) or self._file_size(dest),
        )
        item, _cached = ensure_source_proxy(self.runner, store, item)
        item = self._apply_path_hints(item, path)
        self.media.append(item)
        return item

    def _apply_path_hints(self, item: MediaItem, source: Path) -> MediaItem:
        if item.role is not None or item.shoot_day is not None:
            return item
        hints = hints_from_path(source)
        if hints.role is None and hints.shoot_day is None:
            return item
        card = MediaCard(
            role=hints.role,
            shoot_day=hints.shoot_day,
            confidence=FOLDER_HINT_CONFIDENCE,
            source="folder",
            confirmed=False,
        )
        update: dict = {"card": card}
        if hints.role:
            update["role"] = hints.role
        if hints.shoot_day is not None:
            update["shoot_day"] = hints.shoot_day
        return item.model_copy(update=update)

    def _folder_hints_payload(self, items: list[MediaItem]) -> list[dict]:
        rows: list[dict] = []
        for item in items:
            if item.card is None or item.card.source != "folder":
                continue
            rows.append(
                {
                    "media_id": item.id,
                    "role": item.role,
                    "shoot_day": item.shoot_day,
                    "source": "folder",
                }
            )
        return rows

    def _understand_spans_for_lint(self) -> dict[str, list]:
        spans: dict[str, list] = {}
        for item in self.media:
            cached = load_understand_cache(self._understand_for(item))
            if cached and cached.get("cards"):
                spans[item.id] = list(cached["cards"])
                continue
            path = self._manifest_for(item)
            if path.exists():
                spans[item.id] = load_manifest(path)
        return spans

    def _cluster_cover(self, media_ids: list[str]) -> str | None:
        for mid in media_ids:
            try:
                item = self._media(mid)
            except Exception:
                continue
            key = self._index_summary_for(item).get("keyframe")
            if key:
                return key
        return None

    def _index_summary_for(self, item: MediaItem) -> dict:
        path = self._manifest_for(item)
        if not path.exists():
            return media_index_summary([])
        try:
            return media_index_summary(load_manifest(path))
        except Exception:
            return media_index_summary([])

    def _public_media(self, item: MediaItem) -> dict:
        return public_media(item, index=self._index_summary_for(item))

    def _write_index_sheet(self, items: list[MediaItem]) -> str | None:
        store = self._need()
        thumbs: list[Path] = []
        for item in items:
            summary = self._index_summary_for(item)
            key = summary.get("keyframe")
            if key and Path(key).exists():
                thumbs.append(Path(key))
        if not thumbs:
            return None
        dest = (store.output_dir / "index_sheet.jpg").resolve()
        dest.parent.mkdir(parents=True, exist_ok=True)
        contact_sheet(self.runner, thumbs, dest)
        return str(dest)

    def _index_imported(self, items: list[MediaItem]) -> tuple[int, list[bool], list[str], str | None]:
        """Cheap shot index for newly imported media. Import stays ok even if analyze warns."""
        if not items:
            return 0, [], [], None
        by_id = {item.id: item for item in items}
        targets = [item for item in self.media if item.id in by_id]
        if isinstance(self.runner, FakeRunner) or len(targets) <= 1:
            rows = [self._analyze_one(item) for item in targets]
        else:
            with ThreadPoolExecutor(max_workers=min(4, len(targets))) as pool:
                rows = list(pool.map(self._analyze_one, targets))
        warnings: list[str] = []
        cached: list[bool] = []
        total = 0
        updated: dict[str, MediaItem] = {}
        for count, was_cached, fresh, warning in rows:
            updated[fresh.id] = fresh
            cached.append(was_cached)
            total += count
            if warning:
                warnings.append(warning)
        self.media = [updated.get(item.id, item) for item in self.media]
        self._save_media()
        sheet = self._write_index_sheet([updated.get(item.id, item) for item in targets])
        return total, cached, warnings, sheet

    def import_file(self, path: str, op_id: str | None = None) -> dict:
        store = self._need()
        replay = store.replay(op_id)
        if replay is not None:
            return replay
        item = self._import_path(Path(path))
        self._save_media()
        warns = [w for w in (quality_import_warning(item),) if w]
        shots, cached, index_warns, sheet = self._index_imported([item])
        warns.extend(index_warns)
        result = envelope(True, store.timeline, warns)
        result["media"] = self._public_media(self._media(item.id))
        result["shots"] = shots
        result["cached"] = cached
        result["indexed"] = True
        hints = self._folder_hints_payload([self._media(item.id)])
        if hints:
            result["hints"] = hints
        if sheet:
            result["sheet"] = sheet
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
        warns: list[str] = []
        for item in imported:
            warning = quality_import_warning(item)
            if warning:
                warns.append(warning)
        shots, cached, index_warns, sheet = self._index_imported(imported)
        warns.extend(index_warns)
        result = envelope(True, store.timeline, warns)
        result["media"] = [self._public_media(self._media(m.id)) for m in imported]
        result["imported"] = [str(p) for p in keep]
        result["skipped"] = [str(p) for p in skipped]
        result["deduped"] = burst_ids
        result["shots"] = shots
        result["cached"] = cached
        result["indexed"] = True
        hints = self._folder_hints_payload([self._media(m.id) for m in imported])
        if hints:
            result["hints"] = hints
        if sheet:
            result["sheet"] = sheet
        if op_id:
            store.ledger[op_id] = result
            store.persist()
        return result

    def media_list(
        self,
        shoot_day: int | str | None = None,
        role: str | None = None,
        min_motion: float | None = None,
        sort: str | None = None,
    ) -> dict:
        store = self._need()
        items = list(self.media)
        if shoot_day is not None:
            items = [item for item in items if shoot_days_equal(item.shoot_day, shoot_day)]
        if role is not None:
            items = [item for item in items if roles_equal(item.role, role)]
        summaries = {item.id: self._index_summary_for(item) for item in items}
        if min_motion is not None:
            filtered = []
            for item in items:
                motion = summaries[item.id].get("motion")
                if motion is None:
                    continue
                if float(motion) + 1e-9 >= float(min_motion):
                    filtered.append(item)
            items = filtered
        if sort in (None, "", "captured_at"):
            items = [
                item
                for _, item in sorted(
                    enumerate(items),
                    key=lambda pair: captured_at_sort_key(pair[1].captured_at, pair[0]),
                )
            ]
        result = envelope(True, store.timeline, quality_soft_warnings(items))
        rows = []
        for m in items:
            row = public_media(m, index=summaries.get(m.id))
            row["carded"] = is_carded(m)
            rows.append(row)
        result["media"] = rows
        result["card_coverage"] = card_coverage(self.media)
        return result

    def media_tag(
        self,
        media_id: str,
        shoot_day: int | str | None = None,
        role: str | None = None,
        op_id: str | None = None,
    ) -> dict:
        store = self._need()
        replay = store.replay(op_id)
        if replay is not None:
            return replay
        item = self._media(media_id)
        if shoot_day is None and role is None:
            return envelope(False, store.timeline, ["media_tag requires shoot_day or role"])
        update: dict = {}
        if shoot_day is not None:
            update["shoot_day"] = normalize_shoot_day(shoot_day)
        if role is not None:
            update["role"] = normalize_role(role)
        fresh = item.model_copy(update=update)
        self.media = [fresh if m.id == media_id else m for m in self.media]
        self._save_media()
        result = envelope(True, store.timeline, [])
        result["media"] = self._public_media(fresh)
        if op_id:
            store.ledger[op_id] = result
            store.persist()
        return result

    def shoot_day_suggest(self, apply: bool = False, op_id: str | None = None) -> dict:
        store = self._need()
        if apply:
            replay = store.replay(op_id)
            if replay is not None:
                return replay
        clusters, unclustered = cluster_shoot_days(self.media)
        rows = []
        for cluster in clusters:
            rows.append(
                {
                    "shoot_day": cluster.shoot_day,
                    "media_ids": cluster.media_ids,
                    "start_at": cluster.start_at,
                    "end_at": cluster.end_at,
                    "cover_keyframe": self._cluster_cover(cluster.media_ids),
                }
            )
        applied: list[str] = []
        if apply:
            by_id = {item.id: item for item in self.media}
            updated: list[MediaItem] = []
            for item in self.media:
                day = day_for_media(item.id, clusters)
                if day is None or item.shoot_day is not None:
                    updated.append(item)
                    continue
                card = item.card
                if card is None or not card.confirmed:
                    card = MediaCard(
                        role=item.role or (card.role if card else None),
                        shoot_day=day,
                        subjects=list(card.subjects) if card else [],
                        confidence=card.confidence if card else 0.4,
                        source=card.source if card else "suggested",
                        confirmed=False,
                        note=card.note if card else "",
                    )
                else:
                    card = card.model_copy(update={"shoot_day": card.shoot_day or day})
                fresh = item.model_copy(update={"shoot_day": day, "card": card})
                updated.append(fresh)
                applied.append(item.id)
                by_id[item.id] = fresh
            self.media = updated
            self._save_media()
        result = envelope(True, store.timeline, [])
        result["clusters"] = rows
        result["unclustered"] = unclustered
        result["applied"] = applied
        if apply and op_id:
            store.ledger[op_id] = result
            store.persist()
        return result

    def media_card_propose(self, media_id: str | None = None) -> dict:
        store = self._need()
        targets = [self._media(media_id)] if media_id else [m for m in self.media if m.kind != "audio"]
        clusters, unclustered = cluster_shoot_days(self.media)
        proposals = []
        for item in targets:
            cached = load_understand_cache(self._understand_for(item)) or {}
            cards = list(cached.get("cards") or [])
            shots: list = []
            path = self._manifest_for(item)
            if path.exists():
                shots = load_manifest(path)
            proposals.append(
                propose_card(
                    item,
                    understand_cards=cards,
                    shots=shots,
                    cluster_day=day_for_media(item.id, clusters),
                    peers=self.media,
                )
            )
        result = envelope(True, store.timeline, [])
        result["proposals"] = proposals
        result["card_coverage"] = card_coverage(self.media)
        result["unclustered"] = unclustered
        return result

    def media_card_confirm(
        self,
        media_id: str,
        role: str | None = None,
        shoot_day: int | str | None = None,
        subjects: list[str] | None = None,
        note: str | None = None,
        source: CardSource | None = None,
        op_id: str | None = None,
    ) -> dict:
        store = self._need()
        replay = store.replay(op_id)
        if replay is not None:
            return replay
        item = self._media(media_id)
        final_role = normalize_role(role) if role is not None else item.role
        final_day = normalize_shoot_day(shoot_day) if shoot_day is not None else item.shoot_day
        final_subjects = list(subjects) if subjects is not None else []
        final_note = note or ""
        if item.card is not None:
            if role is None:
                final_role = final_role or item.card.role
            if shoot_day is None and final_day is None:
                final_day = item.card.shoot_day
            if subjects is None:
                final_subjects = list(item.card.subjects)
            if note is None:
                final_note = item.card.note
        if final_role is None and final_day is None and not final_subjects:
            return envelope(
                False,
                store.timeline,
                ["media_card_confirm requires role, shoot_day, or subjects"],
            )
        self._push_label_undo()
        card = MediaCard(
            role=final_role,
            shoot_day=final_day,
            subjects=final_subjects,
            confidence=1.0,
            source=source or "agent",
            confirmed=True,
            note=final_note,
        )
        update: dict = {"card": card}
        if final_role is not None:
            update["role"] = final_role
        if final_day is not None:
            update["shoot_day"] = final_day
        fresh = item.model_copy(update=update)
        self.media = [fresh if m.id == media_id else m for m in self.media]
        self._save_media()
        result = envelope(True, store.timeline, [])
        result["media"] = self._public_media(fresh)
        result["card"] = card.model_dump()
        result["card_coverage"] = card_coverage(self.media)
        if op_id:
            store.ledger[op_id] = result
            store.persist()
        return result

    def label_queue(
        self,
        filter: str = "all",
        shoot_day: int | str | None = None,
        role: str | None = None,
    ) -> dict:
        store = self._need()
        filt = (filter or "all").strip().lower()
        if filt not in QUEUE_FILTERS:
            result = envelope(False, store.timeline, [f"unknown filter {filter}"])
            result["groups"] = []
            result["items"] = []
            result["counts"] = {name: 0 for name in QUEUE_FILTERS}
            return result
        queued = build_label_queue(
            self.media,
            shots_by_media=self._shots_by_media(),
            shot_cards=self.shot_cards,
            understand_by_media=self._understand_by_media(),
            filt=filt,
            shoot_day=shoot_day,
            role=role,
        )
        result = envelope(True, store.timeline, [])
        result.update(queued)
        return result

    def label_get(self, media_id: str | None = None, shot_id: str | None = None) -> dict:
        store = self._need()
        if shot_id:
            item, shot = self._find_shot(shot_id)
            understand = self._understand_by_media().get(item.id) or []
            resolved = resolve_labels(
                item,
                shot,
                shot_card=self.shot_cards.get(shot_id),
                understand_cards=understand,
                peers=self.media,
            )
            result = envelope(True, store.timeline, [])
            result["label"] = resolved
            result["media"] = self._public_media(item)
            result["shot"] = shot.model_dump()
            result["card"] = self.shot_cards.get(shot_id).model_dump() if shot_id in self.shot_cards else None
            return result
        if not media_id:
            return envelope(False, store.timeline, ["label_get requires media_id or shot_id"])
        item = self._media(media_id)
        understand = self._understand_by_media().get(item.id) or []
        resolved = resolve_labels(item, None, understand_cards=understand, peers=self.media)
        shots = []
        for shot in self._shots_by_media().get(item.id) or []:
            shots.append(
                resolve_labels(
                    item,
                    shot,
                    shot_card=self.shot_cards.get(shot.id),
                    understand_cards=understand,
                    peers=self.media,
                )
            )
        result = envelope(True, store.timeline, [])
        result["label"] = resolved
        result["media"] = self._public_media(item)
        result["shot"] = None
        result["shots"] = shots
        result["card"] = item.card.model_dump() if item.card else None
        return result

    def shot_card_confirm(
        self,
        shot_id: str,
        role: str | None = None,
        shoot_day: int | str | None = None,
        subjects: list[str] | None = None,
        note: str | None = None,
        source: CardSource | None = None,
        op_id: str | None = None,
    ) -> dict:
        store = self._need()
        replay = store.replay(op_id)
        if replay is not None:
            return replay
        item, shot = self._find_shot(shot_id)
        existing = self.shot_cards.get(shot_id)
        final_role = normalize_role(role) if role is not None else (existing.role if existing else None)
        final_day = (
            normalize_shoot_day(shoot_day)
            if shoot_day is not None
            else (existing.shoot_day if existing else None)
        )
        final_subjects = list(subjects) if subjects is not None else (list(existing.subjects) if existing else [])
        final_note = note if note is not None else (existing.note if existing else "")
        if final_role is None and final_day is None and not final_subjects:
            return envelope(
                False,
                store.timeline,
                ["shot_card_confirm requires role, shoot_day, or subjects"],
            )
        self._push_label_undo()
        card = ShotCard(
            shot_id=shot.id,
            media_id=item.id,
            role=final_role,
            shoot_day=final_day,
            subjects=final_subjects,
            confidence=1.0,
            source=source or "owner",
            confirmed=True,
            note=final_note,
        )
        self.shot_cards[shot.id] = card
        self._save_shot_cards()
        understand = self._understand_by_media().get(item.id) or []
        result = envelope(True, store.timeline, [])
        result["card"] = card.model_dump()
        result["label"] = resolve_labels(
            item, shot, shot_card=card, understand_cards=understand, peers=self.media
        )
        result["shot"] = shot.model_dump()
        if op_id:
            store.ledger[op_id] = result
            store.persist()
        return result

    def labels_bulk_confirm(self, items: list[dict] | None = None, op_id: str | None = None) -> dict:
        store = self._need()
        replay = store.replay(op_id)
        if replay is not None:
            return replay
        rows = list(items or [])
        if not rows:
            return envelope(False, store.timeline, ["labels_bulk_confirm requires items"])
        self._push_label_undo()
        confirmed: list[dict] = []
        warnings: list[str] = []
        for row in rows:
            if not isinstance(row, dict):
                warnings.append("skip non-object item")
                continue
            shot_id = row.get("shot_id")
            media_id = row.get("media_id")
            kwargs = {
                "role": row.get("role"),
                "shoot_day": row.get("shoot_day"),
                "subjects": row.get("subjects"),
                "note": row.get("note"),
                "source": row.get("source") or "owner",
            }
            if shot_id:
                existing = self.shot_cards.get(str(shot_id))
                try:
                    item, shot = self._find_shot(str(shot_id))
                except Reject as exc:
                    warnings.append(str(exc))
                    continue
                card = ShotCard(
                    shot_id=shot.id,
                    media_id=item.id,
                    role=normalize_role(kwargs["role"]) if kwargs["role"] is not None else (existing.role if existing else None),
                    shoot_day=(
                        normalize_shoot_day(kwargs["shoot_day"])
                        if kwargs["shoot_day"] is not None
                        else (existing.shoot_day if existing else None)
                    ),
                    subjects=(
                        list(kwargs["subjects"])
                        if kwargs["subjects"] is not None
                        else (list(existing.subjects) if existing else [])
                    ),
                    note=kwargs["note"] if kwargs["note"] is not None else (existing.note if existing else ""),
                    confidence=1.0,
                    source=kwargs["source"],
                    confirmed=True,
                )
                if card.role is None and card.shoot_day is None and not card.subjects:
                    warnings.append(f"shot {shot.id} needs role, shoot_day, or subjects")
                    continue
                self.shot_cards[shot.id] = card
                confirmed.append({"scope": "shot", "shot_id": shot.id, "media_id": item.id})
                continue
            if media_id:
                try:
                    item = self._media(str(media_id))
                except Reject as exc:
                    warnings.append(str(exc))
                    continue
                card = MediaCard(
                    role=normalize_role(kwargs["role"]) if kwargs["role"] is not None else item.role,
                    shoot_day=(
                        normalize_shoot_day(kwargs["shoot_day"])
                        if kwargs["shoot_day"] is not None
                        else item.shoot_day
                    ),
                    subjects=list(kwargs["subjects"] or (item.card.subjects if item.card else [])),
                    note=kwargs["note"] if kwargs["note"] is not None else (item.card.note if item.card else ""),
                    confidence=1.0,
                    source=kwargs["source"],
                    confirmed=True,
                )
                if item.card is not None:
                    if kwargs["role"] is None:
                        card = card.model_copy(update={"role": card.role or item.card.role})
                    if kwargs["shoot_day"] is None:
                        card = card.model_copy(update={"shoot_day": card.shoot_day if card.shoot_day is not None else item.card.shoot_day})
                    if kwargs["subjects"] is None:
                        card = card.model_copy(update={"subjects": list(item.card.subjects)})
                    if kwargs["note"] is None:
                        card = card.model_copy(update={"note": item.card.note})
                if card.role is None and card.shoot_day is None and not card.subjects:
                    warnings.append(f"media {item.id} needs role, shoot_day, or subjects")
                    continue
                update: dict = {"card": card}
                if card.role is not None:
                    update["role"] = card.role
                if card.shoot_day is not None:
                    update["shoot_day"] = card.shoot_day
                fresh = item.model_copy(update=update)
                self.media = [fresh if m.id == item.id else m for m in self.media]
                confirmed.append({"scope": "media", "media_id": item.id})
                continue
            warnings.append("item requires media_id or shot_id")
        self._save_media()
        self._save_shot_cards()
        result = envelope(True, store.timeline, warnings)
        result["confirmed"] = confirmed
        result["card_coverage"] = card_coverage(self.media)
        if op_id:
            store.ledger[op_id] = result
            store.persist()
        return result

    def labels_clear(
        self,
        media_id: str | None = None,
        shot_id: str | None = None,
        op_id: str | None = None,
    ) -> dict:
        store = self._need()
        replay = store.replay(op_id)
        if replay is not None:
            return replay
        if media_id is None and shot_id is None:
            return envelope(False, store.timeline, ["labels_clear requires media_id or shot_id"])
        self._push_label_undo()
        cleared: list[str] = []
        if shot_id:
            if shot_id in self.shot_cards:
                del self.shot_cards[shot_id]
                cleared.append(shot_id)
            else:
                return envelope(False, store.timeline, [f"unknown shot card {shot_id}"])
        if media_id:
            item = self._media(media_id)
            fresh = item.model_copy(update={"card": None})
            self.media = [fresh if m.id == media_id else m for m in self.media]
            cleared.append(media_id)
            if shot_id is None:
                for sid, card in list(self.shot_cards.items()):
                    if card.media_id == media_id:
                        del self.shot_cards[sid]
                        cleared.append(sid)
        self._save_media()
        self._save_shot_cards()
        result = envelope(True, store.timeline, [])
        result["cleared"] = cleared
        result["card_coverage"] = card_coverage(self.media)
        if op_id:
            store.ledger[op_id] = result
            store.persist()
        return result

    def labels_undo(self, op_id: str | None = None) -> dict:
        store = self._need()
        replay = store.replay(op_id)
        if replay is not None:
            return replay
        if not self.label_history:
            return envelope(False, store.timeline, ["nothing to undo"])
        snap = self.label_history.pop()
        self._restore_label_snapshot(snap)
        self._save_label_history()
        result = envelope(True, store.timeline, [])
        result["card_coverage"] = card_coverage(self.media)
        result["shot_overrides"] = len(self.shot_cards)
        if op_id:
            store.ledger[op_id] = result
            store.persist()
        return result

    def label_conflicts(self) -> dict:
        store = self._need()
        rows = collect_conflicts(
            self.media,
            shots_by_media=self._shots_by_media(),
            shot_cards=self.shot_cards,
            understand_by_media=self._understand_by_media(),
        )
        result = envelope(True, store.timeline, [])
        result["conflicts"] = rows
        return result

    def label_readiness(self) -> dict:
        store = self._need()
        payload = readiness_payload(
            self.media,
            shots_by_media=self._shots_by_media(),
            shot_cards=self.shot_cards,
            understand_by_media=self._understand_by_media(),
        )
        result = envelope(True, store.timeline, [])
        result.update(payload)
        return result

    def media_remove(self, media_id: str, op_id: str | None = None) -> dict:
        store = self._need()
        from lc_editor.models import clip_media_ids

        used = [c.id for c in store.timeline.clips if media_id in clip_media_ids(c)]
        used += [layer.id for layer in store.timeline.layers if layer.media_id == media_id]
        used += [track.id for track in store.timeline.music if track.media_id == media_id]
        if used:
            return envelope(False, store.timeline, [f"SPEC-SES-05: media still used by clips {used}"])
        self.media = [m for m in self.media if m.id != media_id]
        for sid, card in list(self.shot_cards.items()):
            if card.media_id == media_id:
                del self.shot_cards[sid]
        self._save_media()
        self._save_shot_cards()
        return envelope(True, store.timeline, [])

    def probe(self, media_id: str | None = None, path: str | None = None) -> dict:
        store = self._need()
        if media_id:
            item = self._media(media_id)
            info = public_media(item)
        else:
            info = public_media(self._probe_file(Path(path or "")))
        result = envelope(True, store.timeline, quality_soft_warnings([info]))
        result["probe"] = info
        return result

    def _lint_media(self) -> list:
        store = self._need()
        ff = "ffmpeg" if isinstance(self.runner, FakeRunner) else find_tool("ffmpeg")
        out = []
        for item in self.media:
            work = working_media(item)
            src = Path(work.path)
            if src.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}:
                out.append(work.model_copy(update={"path": str(src), "kind": "image"}))
                continue
            still = store.stills_dir / f"{item.id}_lint.jpg"
            still.parent.mkdir(parents=True, exist_ok=True)
            if not still.exists() or still.stat().st_size < 200:
                self.runner.run(extract_frame_args(ff, src, still, kind="video", seek_s=0.1))
            if (not still.exists() or still.stat().st_size < 200) and item.kind == "image":
                out.append(item.model_copy(update={"path": item.path, "kind": "image"}))
                continue
            if still.exists() and still.stat().st_size >= 200:
                out.append(work.model_copy(update={"path": str(still), "kind": "image"}))
            else:
                out.append(work)
        return out

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
        return self.media_proxy(media_id=media_id)

    def media_proxy(self, media_id: str | None = None, op_id: str | None = None) -> dict:
        store = self._need()
        targets = [self._media(media_id)] if media_id else list(self.media)
        paths = []
        cached = []
        updated = []
        for item in targets:
            fresh, was_cached = ensure_source_proxy(self.runner, store, item)
            updated.append(fresh)
            paths.append(fresh.proxy_path)
            cached.append(was_cached)
        by_id = {m.id: m for m in updated}
        self.media = [by_id.get(m.id, m) for m in self.media]
        self._save_media()
        result = envelope(True, store.timeline, [])
        result["paths"] = paths
        result["cached"] = cached
        return result

    def _proxy_key(self, item: MediaItem) -> str:
        src = Path(item.path)
        if not src.exists():
            src = Path(item.original_path)
        if src.exists():
            return source_proxy_hash(src)
        return item.id

    def _manifest_for(self, item: MediaItem) -> Path:
        return manifest_path(self._need().analysis_dir, self._proxy_key(item))

    def _understand_for(self, item: MediaItem) -> Path:
        return understand_path(self._need().analysis_dir, self._proxy_key(item))

    def _extract_keyframe(self, item: MediaItem, dest: Path, seek_s: float) -> None:
        dest.parent.mkdir(parents=True, exist_ok=True)
        src = Path(item.path)
        if not src.exists():
            src = Path(item.original_path)
        if item.kind == "image":
            try:
                from PIL import Image

                image = Image.open(src).convert("RGB")
                image = image.resize((SOURCE_PROXY_W, SOURCE_PROXY_H))
                image.save(dest, "JPEG")
                if dest.exists() and dest.stat().st_size > 0:
                    return
            except Exception:
                pass
        ff = "ffmpeg" if isinstance(self.runner, FakeRunner) else find_tool("ffmpeg")
        work = working_media(item)
        work_src = Path(work.path)
        kind = "image" if item.kind == "image" or work_src.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"} else "video"
        seek = None if kind == "image" else max(0.0, seek_s)
        args = extract_frame_args(
            ff,
            work_src,
            dest,
            kind=kind,
            seek_s=seek,
            scale=(SOURCE_PROXY_W, SOURCE_PROXY_H),
        )
        self.runner.run(args)
        if (not dest.exists() or dest.stat().st_size < 100) and isinstance(self.runner, FakeRunner):
            dest.write_bytes(b"\xff\xd8\xff" + b"\x00" * 120 + b"\xd9")

    def _analyze_one(self, item: MediaItem) -> tuple[int, bool, MediaItem, str | None]:
        store = self._need()
        store.analysis_dir.mkdir(parents=True, exist_ok=True)
        store.keyframes_dir.mkdir(parents=True, exist_ok=True)
        fresh, _proxy_cached = ensure_source_proxy(self.runner, store, item)
        dest = manifest_path(store.analysis_dir, self._proxy_key(fresh))
        if dest.exists() and dest.stat().st_size > 0:
            return len(load_manifest(dest)), True, fresh, None
        if fresh.kind == "image":
            sid = shot_id(self._proxy_key(fresh), 0)
            keyframe = store.keyframes_dir / f"{sid}.jpg"
            self._extract_keyframe(fresh, keyframe, 0.0)
            shot = Shot(
                id=sid,
                media_id=fresh.id,
                in_s=0.0,
                out_s=DEFAULT_STILL_S,
                duration_s=DEFAULT_STILL_S,
                keyframe=str(keyframe.resolve()),
                metrics=metrics_for_span([], [], 0.0, DEFAULT_STILL_S, keyframe, has_audio=False),
            )
            write_manifest(dest, [shot])
            return 1, False, fresh, None
        ff = "ffmpeg" if isinstance(self.runner, FakeRunner) else find_tool("ffmpeg")
        key = self._proxy_key(fresh)
        args = analysis_pass_args(
            ff,
            fresh.proxy_path or fresh.path,
            has_audio=fresh.has_audio,
        )
        ran = self.runner.run(args)
        if ran.returncode != 0:
            return 0, False, fresh, f"SPEC-ANA-08: analysis failed for {fresh.id}: {ran.stderr or 'ffmpeg failed'}"
        text = f"{ran.stderr or ''}\n{ran.stdout or ''}"
        events = parse_scdet(text)
        signal = parse_signalstats(text)
        if not signal:
            return 0, False, fresh, f"SPEC-ANA-08: empty metadata for {fresh.id}"
        audio = parse_astats(text) if fresh.has_audio else []
        spans = segment_shots(events, fresh.duration_s)
        shots: list[Shot] = []
        for index, (in_s, out_s) in enumerate(spans):
            sid = shot_id(key, index)
            keyframe = store.keyframes_dir / f"{sid}.jpg"
            self._extract_keyframe(fresh, keyframe, (in_s + out_s) / 2)
            shots.append(
                Shot(
                    id=sid,
                    media_id=fresh.id,
                    in_s=in_s,
                    out_s=out_s,
                    duration_s=round(out_s - in_s, 4),
                    keyframe=str(keyframe.resolve()),
                    metrics=metrics_for_span(
                        signal,
                        audio,
                        in_s,
                        out_s,
                        keyframe,
                        has_audio=fresh.has_audio,
                    ),
                )
            )
        write_manifest(dest, shots)
        return len(shots), False, fresh, None

    def media_analyze(self, media_id: str | None = None, op_id: str | None = None) -> dict:
        store = self._need()
        replay = store.replay(op_id)
        if replay is not None:
            return replay
        targets = [self._media(media_id)] if media_id else list(self.media)
        if not targets:
            result = envelope(True, store.timeline, [])
            result["shots"] = 0
            result["cached"] = []
            if op_id:
                store.ledger[op_id] = result
                store.persist()
            return result

        def run_one(item: MediaItem) -> tuple[int, bool, MediaItem, str | None]:
            return self._analyze_one(item)

        if isinstance(self.runner, FakeRunner) or len(targets) <= 1:
            rows = [run_one(item) for item in targets]
        else:
            with ThreadPoolExecutor(max_workers=min(4, len(targets))) as pool:
                rows = list(pool.map(run_one, targets))

        warnings: list[str] = []
        cached: list[bool] = []
        total = 0
        updated: dict[str, MediaItem] = {}
        failed = False
        for count, was_cached, fresh, warning in rows:
            updated[fresh.id] = fresh
            cached.append(was_cached)
            total += count
            if warning:
                failed = True
                warnings.append(warning)
        self.media = [updated.get(item.id, item) for item in self.media]
        self._save_media()
        target_ids = {item.id for item in targets}
        warnings.extend(quality_soft_warnings(item for item in self.media if item.id in target_ids))
        result = envelope(not failed, store.timeline, warnings)
        result["shots"] = total
        result["cached"] = cached
        if op_id:
            store.ledger[op_id] = result
            store.persist()
        return result

    def _understand_one(
        self,
        item: MediaItem,
        *,
        roles: list[str],
        budget: int,
        first_media_id: str | None,
        sizes: dict[str, tuple[int, int]],
        query: str | None = None,
        selection: str = DEFAULT_SELECTION,
    ) -> tuple[list[dict], list[str], float]:
        warnings: list[str] = []
        path = self._manifest_for(item)
        if not path.exists():
            count, _cached, fresh, warning = self._analyze_one(item)
            if warning:
                return [], [warning], 0.0
            if count == 0:
                return [], [f"not analyzed: {fresh.id}"], 0.0
            item = fresh
            path = self._manifest_for(item)
        shots = load_manifest(path)
        if not shots:
            return [], [f"not analyzed: {item.id}"], 0.0
        duration = media_duration_s(shots)
        if duration <= 0 and item.duration_s:
            duration = float(item.duration_s)
        # Score without prior understand tags so re-runs stay stable.
        clean = [
            s.model_copy(
                update={"tags": [t for t in (s.tags or []) if not str(t).startswith("understand:")]}
            )
            for s in shots
        ]
        candidates = select_adaptive_shots(
            clean,
            budget,
            query=query,
            roles=roles,
            selection=selection,
            first_media_id=first_media_id,
            sizes=sizes,
            embedder=optional_embedder(),
        )
        cards = [
            card_from_shot(
                shot,
                roles,
                first_media_id=first_media_id,
                sizes=sizes,
                media_role=item.role,
            )
            for shot in candidates
        ]
        cards.sort(key=lambda c: (-float(c["score"]), c["in_s"], c["shot_id"]))
        tagged = apply_understand_tags(clean, cards)
        write_manifest(path, tagged)
        payload = {
            "media_id": item.id,
            "query_roles": roles,
            "budget_frames": budget,
            "frames_scored": len(cards),
            "selection": normalize_selection(selection),
            "duration_s": duration,
            "cards": [{k: v for k, v in card.items() if k != "shot_id"} for card in cards],
            "cards_internal": cards,
        }
        write_understand_cache(self._understand_for(item), payload)
        public = [{k: v for k, v in card.items() if k != "shot_id"} for card in cards]
        return public, warnings, duration

    def media_understand(
        self,
        media_id: str | None = None,
        query: str | None = None,
        budget_frames: int | None = None,
        roles: list[str] | None = None,
        shared_budget: bool = False,
        selection: str | None = None,
    ) -> dict:
        """Cheap hierarchical understanding from the import shot index.

        Train B default selection is adaptive (FOCUS coarse→fine; AKS relevance
        + coverage when ``query`` is concrete). Pass ``selection="legacy"`` for
        Train A coverage+peaks, or ``"uniform"`` for the even grid baseline.
        ``shared_budget=True`` splits one frame pool across all imported video.
        No full-video VLM. Optional CLIP/BLIP only when LC_EDITOR_VISION is set
        and weights are already installable offline.
        """
        store = self._need()
        mode = normalize_selection(selection)
        role_list = resolve_understand_roles(query=query, roles=roles)
        targets = [self._media(media_id)] if media_id else list(self.media)
        visual = [item for item in targets if item.kind != "audio"]
        use_shared = bool(shared_budget) and media_id is None and len(visual) > 1
        if use_shared:
            budget = clamp_shared_budget(budget_frames)
        else:
            budget = clamp_budget(budget_frames)
        if not targets:
            result = envelope(True, store.timeline, [])
            result["spans"] = []
            result["budget_frames"] = budget
            result["frames_scored"] = 0
            result["roles"] = role_list
            result["query"] = query or "process"
            result["selection"] = mode
            result["shared_budget"] = False
            result["metrics"] = understand_cost_metrics(0, 0.0, selection=mode, shared_budget=False)
            result["embedder"] = embedder_status()
            return result
        first = self.media[0].id if self.media else None
        sizes = {item.id: (item.width, item.height) for item in self.media}

        # Preload manifests so shared budget can weight by duration.
        per_budget: dict[str, int] = {}
        if use_shared:
            durations: list[float] = []
            ids: list[str] = []
            for item in visual:
                path = self._manifest_for(item)
                if not path.exists():
                    count, _cached, fresh, warning = self._analyze_one(item)
                    if warning or count == 0:
                        durations.append(max(0.01, float(item.duration_s or 1.0)))
                        ids.append(item.id)
                        continue
                    item = fresh
                shots = load_manifest(self._manifest_for(item))
                dur = media_duration_s(shots) or float(item.duration_s or 1.0)
                durations.append(max(0.01, dur))
                ids.append(item.id)
            shares = allocate_shared_budget(durations, budget)
            per_budget = dict(zip(ids, shares, strict=True))

        spans: list[dict] = []
        warnings: list[str] = []
        frames_scored = 0
        total_duration = 0.0
        for item in targets:
            if item.kind == "audio":
                continue
            local_budget = per_budget.get(item.id, budget) if use_shared else budget
            if local_budget <= 0:
                continue
            cards, local_warn, duration = self._understand_one(
                item,
                roles=role_list,
                budget=local_budget,
                first_media_id=first,
                sizes=sizes,
                query=query,
                selection=mode,
            )
            warnings.extend(local_warn)
            spans.extend(cards)
            frames_scored += len(cards)
            total_duration += duration
        spans.sort(key=lambda c: (-float(c["score"]), c["media_id"], c["in_s"]))
        metrics = understand_cost_metrics(
            frames_scored,
            total_duration,
            selection=mode,
            shared_budget=use_shared,
        )
        result = envelope(True, store.timeline, warnings)
        result["spans"] = spans
        result["budget_frames"] = budget
        result["frames_scored"] = frames_scored
        result["roles"] = role_list
        result["query"] = query or "process"
        result["selection"] = mode
        result["shared_budget"] = use_shared
        result["metrics"] = metrics
        result["embedder"] = embedder_status()
        return result

    def media_understand_refine(
        self,
        media_id: str,
        in_s: float,
        out_s: float,
        reason: str | None = None,
        budget_frames: int | None = None,
        spatial: bool = False,
    ) -> dict:
        """Dense local re-sample inside one span when the agent is uncertain.

        Pass ``spatial=True`` to also run LENS-lite focus hints on densified
        windows (Train D). Temporal refine alone remains the default.
        """
        store = self._need()
        item = self._media(media_id)
        budget = clamp_budget(budget_frames, default=DEFAULT_REFINE_BUDGET)
        start = round(float(in_s), 4)
        end = round(float(out_s), 4)
        if end <= start:
            result = envelope(False, store.timeline, ["out_s must be greater than in_s"])
            result["spans"] = []
            return result
        path = self._manifest_for(item)
        if not path.exists():
            count, _cached, fresh, warning = self._analyze_one(item)
            if warning:
                result = envelope(False, store.timeline, [warning])
                result["spans"] = []
                return result
            item = fresh
            path = self._manifest_for(item)
        shots = load_manifest(path)
        windows = refine_windows(start, end, budget)
        roles = resolve_understand_roles(query="process")
        cached = load_understand_cache(self._understand_for(item)) or {}
        if cached.get("query_roles"):
            roles = list(cached["query_roles"])
        first = self.media[0].id if self.media else None
        sizes = {item.id: (item.width, item.height) for item in self.media}
        cards: list[dict] = []
        for index, (win_in, win_out) in enumerate(windows):
            parent = parent_shot_for_span(shots, win_in, win_out)
            if parent is None:
                continue
            sid = f"{self._proxy_key(item)}_u{index}_{int(win_in * 1000)}"
            keyframe = store.keyframes_dir / f"{sid}.jpg"
            mid = (win_in + win_out) / 2.0
            self._extract_keyframe(item, keyframe, mid)
            sharp = round(keyframe_sharpness(keyframe), 4)
            metrics = parent.metrics.model_copy(
                update={
                    "sharpness": sharp,
                    "blur": round(max(0.0, min(1.0, 1.0 - sharp)), 4),
                }
            )
            pseudo = Shot(
                id=sid,
                media_id=item.id,
                in_s=win_in,
                out_s=win_out,
                duration_s=round(win_out - win_in, 4),
                keyframe=str(keyframe.resolve()),
                metrics=metrics,
                tags=list(parent.tags or []),
            )
            card = card_from_shot(
                pseudo, roles, first_media_id=first, sizes=sizes, media_role=item.role
            )
            if spatial:
                card = annotate_span_spatial(card, keyframe)
            if reason:
                card["reason"] = f"{reason}; {card['reason']}"
            cards.append(card)
        cards.sort(key=lambda c: (-float(c["score"]), c["in_s"], c.get("shot_id", "")))
        # Prefer the best refine window's role on the parent overlapping shot.
        if cards:
            best = cards[0]
            mid = (float(best["in_s"]) + float(best["out_s"])) / 2.0
            stamped = []
            for shot in shots:
                tags = [t for t in (shot.tags or []) if not str(t).startswith("understand:")]
                if shot.in_s - 1e-6 <= mid < shot.out_s + 1e-6:
                    tag = f"understand:{best['role_hint']}"
                    tags.append(tag)
                stamped.append(shot.model_copy(update={"tags": tags}))
            write_manifest(path, stamped)
        public = [{k: v for k, v in card.items() if k != "shot_id"} for card in cards]
        payload = {
            **(cached or {}),
            "media_id": item.id,
            "refined": {
                "in_s": start,
                "out_s": end,
                "reason": reason,
                "budget_frames": budget,
                "spatial": bool(spatial),
                "spans": public,
            },
        }
        if spatial and public:
            payload["spatial"] = {
                "budget_frames": budget,
                "reason": reason or "refine+spatial",
                "spans": public,
                "from_refine": True,
            }
        write_understand_cache(self._understand_for(item), payload)
        result = envelope(True, store.timeline, [])
        result["spans"] = public
        result["budget_frames"] = budget
        result["frames_scored"] = len(public)
        result["in_s"] = start
        result["out_s"] = end
        result["selection"] = "refine_spatial" if spatial else "refine"
        result["spatial"] = bool(spatial)
        result["metrics"] = understand_cost_metrics(
            len(public),
            max(0.0, end - start),
            selection="adaptive",
            shared_budget=False,
        )
        result["embedder"] = embedder_status()
        return result

    def media_understand_spatial(
        self,
        media_id: str | None = None,
        in_s: float | None = None,
        out_s: float | None = None,
        budget_frames: int | None = None,
        reason: str | None = None,
    ) -> dict:
        """LENS-lite spatial densify for high-value ambiguous spans.

        Detects busy / low-dominance keyframes, densely samples inside the
        span, and soft-suggests ``focus_x`` / ``focus_y`` for cover crop.
        Never blocks export. No VLM weights.
        """
        store = self._need()
        budget = clamp_spatial_budget(budget_frames)
        targets = [self._media(media_id)] if media_id else list(self.media)
        visual = [item for item in targets if item.kind != "audio"]
        warnings: list[str] = []
        spans: list[dict] = []
        frames_scored = 0
        first = self.media[0].id if self.media else None
        sizes = {item.id: (item.width, item.height) for item in self.media}

        for item in visual:
            path = self._manifest_for(item)
            if not path.exists():
                count, _cached, fresh, warning = self._analyze_one(item)
                if warning:
                    warnings.append(warning)
                    continue
                if count == 0:
                    warnings.append(f"not analyzed: {fresh.id}")
                    continue
                item = fresh
                path = self._manifest_for(item)
            shots = load_manifest(path)
            cached = load_understand_cache(self._understand_for(item)) or {}
            roles = resolve_understand_roles(query="process")
            if cached.get("query_roles"):
                roles = list(cached["query_roles"])

            work_spans: list[dict] = []
            if in_s is not None and out_s is not None:
                start = round(float(in_s), 4)
                end = round(float(out_s), 4)
                if end <= start:
                    warnings.append("out_s must be greater than in_s")
                    continue
                parent = parent_shot_for_span(shots, start, end)
                if parent is None:
                    warnings.append(f"no shot for span on {item.id}")
                    continue
                seed = card_from_shot(
                    parent, roles, first_media_id=first, sizes=sizes, media_role=item.role
                )
                seed["in_s"] = start
                seed["out_s"] = end
                work_spans = [annotate_span_spatial(seed)]
            else:
                cards = list(cached.get("cards") or [])
                if not cards:
                    understood = self.media_understand(media_id=item.id, budget_frames=budget)
                    cards = list(understood.get("spans") or [])
                    warnings.extend(understood.get("warnings") or [])
                work_spans = select_spatial_targets(cards)
                if not work_spans:
                    # Still annotate top cards so agents see focus hints.
                    ranked = sorted(cards, key=lambda c: (-float(c.get("score") or 0.0), c.get("in_s", 0)))
                    work_spans = [annotate_span_spatial(c) for c in ranked[:3]]

            local_spans: list[dict] = []
            for seed in work_spans:
                start = round(float(seed.get("in_s", 0.0)), 4)
                end = round(float(seed.get("out_s", start + 1.0)), 4)
                windows = spatial_windows(start, end, budget)
                window_cards: list[dict] = []
                for index, (win_in, win_out) in enumerate(windows):
                    parent = parent_shot_for_span(shots, win_in, win_out)
                    if parent is None:
                        continue
                    sid = f"{self._proxy_key(item)}_s{index}_{int(win_in * 1000)}"
                    keyframe = store.keyframes_dir / f"{sid}.jpg"
                    mid = (win_in + win_out) / 2.0
                    self._extract_keyframe(item, keyframe, mid)
                    sharp = round(keyframe_sharpness(keyframe), 4)
                    metrics = parent.metrics.model_copy(
                        update={
                            "sharpness": sharp,
                            "blur": round(max(0.0, min(1.0, 1.0 - sharp)), 4),
                        }
                    )
                    pseudo = Shot(
                        id=sid,
                        media_id=item.id,
                        in_s=win_in,
                        out_s=win_out,
                        duration_s=round(win_out - win_in, 4),
                        keyframe=str(keyframe.resolve()),
                        metrics=metrics,
                        tags=list(parent.tags or []),
                    )
                    card = card_from_shot(
                        pseudo, roles, first_media_id=first, sizes=sizes, media_role=item.role
                    )
                    card = annotate_span_spatial(card, keyframe)
                    if reason:
                        card["reason"] = f"{reason}; {card['reason']}"
                    card["spatial_densified"] = True
                    window_cards.append(card)
                if not window_cards:
                    annotated = annotate_span_spatial(seed)
                    annotated["spatial_densified"] = False
                    local_spans.append(annotated)
                    continue
                window_cards.sort(
                    key=lambda c: (
                        -float((c.get("focus_hint") or {}).get("confidence") or 0.0),
                        -float(c.get("score") or 0.0),
                        c.get("in_s", 0.0),
                    )
                )
                best = dict(window_cards[0])
                best["in_s"] = start
                best["out_s"] = end
                best["spatial_windows"] = [
                    {k: v for k, v in w.items() if k != "shot_id"} for w in window_cards
                ]
                best["spatial_densified"] = True
                if seed.get("spatial_ambiguous"):
                    best["spatial_ambiguous"] = True
                local_spans.append({k: v for k, v in best.items() if k != "shot_id"})
                frames_scored += len(window_cards)

            spans.extend(local_spans)
            payload = {
                **(cached or {}),
                "media_id": item.id,
                "spatial": {
                    "budget_frames": budget,
                    "reason": reason,
                    "spans": local_spans,
                },
            }
            write_understand_cache(self._understand_for(item), payload)

        spans.sort(
            key=lambda c: (
                -float(c.get("score") or 0.0),
                str(c.get("media_id") or ""),
                float(c.get("in_s") or 0.0),
            )
        )
        result = envelope(True, store.timeline, warnings)
        result["spans"] = spans
        result["budget_frames"] = budget
        result["frames_scored"] = frames_scored
        result["selection"] = "spatial"
        result["metrics"] = understand_cost_metrics(
            frames_scored,
            sum(max(0.0, float(s.get("out_s", 0)) - float(s.get("in_s", 0))) for s in spans) or 0.0,
            selection="adaptive",
            shared_budget=False,
        )
        result["embedder"] = embedder_status()
        return result

    def _spatial_hint_for_clip(self, clip) -> dict | None:
        """Lookup soft focus hint from understand spatial cache for a clip."""
        try:
            item = self._media(clip.media_id)
        except Reject:
            return None
        cached = load_understand_cache(self._understand_for(item)) or {}
        spatial = cached.get("spatial") or {}
        return pick_hint_for_span(
            spatial,
            media_id=item.id,
            in_s=float(getattr(clip, "in_s", 0.0) or 0.0),
            out_s=float(getattr(clip, "out_s", getattr(clip, "in_s", 0.0)) or 0.0),
        )

    def understand_timeline(
        self,
        media_id: str | None = None,
        top_per_role: int = 2,
        roles: list[str] | None = None,
        refresh: bool = False,
    ) -> dict:
        """Director feed: role-labeled story beats from understand spans.

        Prefers ``*.understand.json`` cards; falls back to ``understand:{role}``
        shot tags. Does not watch frames and does not mutate the timeline.
        """
        store = self._need()
        role_list = resolve_understand_roles(roles=roles) if roles else list(PROCESS_STORY_ORDER)
        try:
            per_role = max(1, int(top_per_role))
        except (TypeError, ValueError):
            per_role = 2
        targets = [self._media(media_id)] if media_id else list(self.media)
        visual = [item for item in targets if item.kind != "audio"]
        warnings: list[str] = []
        if refresh:
            refreshed = self.media_understand(media_id=media_id, roles=role_list)
            if not refreshed.get("ok", True):
                warnings.extend(refreshed.get("warnings") or [])
        media_meta = {
            item.id: {
                "shoot_day": item.shoot_day,
                "role": item.role,
                "captured_at": item.captured_at,
            }
            for item in self.media
        }
        cards: list[dict] = []
        from_cache = 0
        for item in visual:
            cached = load_understand_cache(self._understand_for(item))
            if cached and cached.get("cards"):
                for card in cached["cards"]:
                    cards.append({**card, "source": "understand"})
                from_cache += len(cached["cards"])
                continue
            path = self._manifest_for(item)
            if path.exists():
                tagged = cards_from_tagged_shots(load_manifest(path), media_meta=media_meta)
                cards.extend(tagged)
            else:
                warnings.append(f"not analyzed: {item.id}")
        if not cards and visual:
            warnings.append("no understand spans; call media_understand first")
        timeline = build_understand_timeline(
            cards,
            media_meta=media_meta,
            top_per_role=per_role,
            roles=role_list,
        )
        result = envelope(True, store.timeline, warnings)
        result.update(timeline)
        result["spans"] = cards
        result["frames_scored"] = from_cache or len(cards)
        result["roles"] = role_list
        result["from_cache"] = from_cache > 0
        return result

    def highlights_suggest(
        self,
        target_s: float,
        style: Annotated[
            Literal["process", "reel"],
            Field(description="process: detailing ASMR arc; reel: short-form target with same arc preference"),
        ] = "process",
        media_id: str | None = None,
        refresh: bool = False,
    ) -> dict:
        """Ranked candidate beat sheets from understand spans (Train E).

        Prefers transformation arcs (before → process ASMR → after) over
        virality / transcript hacks. Detailing is often silent: speech peaks
        are not required. Uses Train A–D understand cache, roles, and spatial
        hints when present. Suggest only: does not mutate the timeline and
        does not auto-export. Agent still locks the story.
        """
        store = self._need()
        style_norm = normalize_style(style)
        target = clamp_target_s(target_s, style_norm)
        warnings: list[str] = []
        if refresh:
            refreshed = self.media_understand(media_id=media_id)
            if not refreshed.get("ok", True):
                warnings.extend(refreshed.get("warnings") or [])
        targets = [self._media(media_id)] if media_id else list(self.media)
        visual = [item for item in targets if item.kind != "audio"]
        media_meta = {
            item.id: {
                "shoot_day": item.shoot_day,
                "role": item.role,
                "captured_at": item.captured_at,
            }
            for item in self.media
        }
        cards: list[dict] = []
        spatial_by_media: dict[str, dict] = {}
        from_cache = 0
        for item in visual:
            cached = load_understand_cache(self._understand_for(item))
            if cached and cached.get("cards"):
                for card in cached["cards"]:
                    info = media_meta.get(item.id) or {}
                    cards.append(
                        {
                            **card,
                            "source": card.get("source") or "understand",
                            "shoot_day": card.get("shoot_day", info.get("shoot_day")),
                            "media_role": card.get("media_role", info.get("role")),
                            "captured_at": card.get("captured_at", info.get("captured_at")),
                        }
                    )
                from_cache += len(cached["cards"])
                if cached.get("spatial"):
                    spatial_by_media[item.id] = cached["spatial"]
                continue
            path = self._manifest_for(item)
            if path.exists():
                tagged = cards_from_tagged_shots(load_manifest(path), media_meta=media_meta)
                cards.extend(tagged)
            else:
                warnings.append(f"not analyzed: {item.id}")
        if not cards and visual:
            # Auto-understand once so suggest stays useful without a prior call.
            understood = self.media_understand(media_id=media_id)
            warnings.extend(understood.get("warnings") or [])
            cards = list(understood.get("spans") or [])
            from_cache = 0
            for item in visual:
                cached = load_understand_cache(self._understand_for(item)) or {}
                if cached.get("spatial"):
                    spatial_by_media[item.id] = cached["spatial"]
        if not cards:
            warnings.append("no understand spans; call media_understand first")
        candidates = suggest_highlight_sheets(
            cards,
            target_s=target,
            style=style_norm,
            spatial_by_media=spatial_by_media or None,
        )
        result = envelope(True, store.timeline, warnings)
        result["candidates"] = candidates
        result["style"] = style_norm
        result["target_s"] = target
        result["spans"] = cards
        result["from_cache"] = from_cache > 0
        result["suggest_only"] = True
        result["auto_export"] = False
        result["reason"] = (
            "LC-native beat sheets from understand spans; agent locks story; "
            "does not auto-export"
        )
        return result

    def _load_shots(self, media_id: str | None = None) -> tuple[list[Shot], list[str]]:
        items = [self._media(media_id)] if media_id else list(self.media)
        shots: list[Shot] = []
        warnings: list[str] = []
        missing = False
        for item in items:
            path = self._manifest_for(item)
            if not path.exists():
                missing = True
                continue
            shots.extend(load_manifest(path))
        if missing:
            warnings.append("not analyzed")
        return shots, warnings

    def shots_list(self, media_id: str | None = None) -> dict:
        store = self._need()
        shots, warnings = self._load_shots(media_id)
        result = envelope(True, store.timeline, warnings)
        result["shots"] = [shot.model_dump() for shot in shots]
        return result

    def shots_search(
        self,
        media_id: str | None = None,
        min_duration_s: float | None = None,
        max_duration_s: float | None = None,
        min_motion: float | None = None,
        max_motion: float | None = None,
        audio_class: str | None = None,
        kind: str | None = None,
        shoot_day: int | str | None = None,
        role: str | None = None,
        sort: str | None = None,
        limit: int | None = None,
    ) -> dict:
        store = self._need()
        reason = contradictory_filters(min_duration_s, max_duration_s, min_motion, max_motion)
        if reason:
            result = envelope(False, store.timeline, [reason])
            result["shots"] = []
            return result
        shots, warnings = self._load_shots(media_id)
        kinds = {item.id: item.kind for item in self.media}
        filtered = filter_shots(
            shots,
            min_duration_s=min_duration_s,
            max_duration_s=max_duration_s,
            min_motion=min_motion,
            max_motion=max_motion,
            audio_class=audio_class,
            kinds=kinds,
            kind=kind,
        )
        if shoot_day is not None or role is not None:
            media_by_id = {item.id: item for item in self.media}
            understand = self._understand_by_media()

            def _matches(shot: Shot) -> bool:
                item = media_by_id.get(shot.media_id)
                resolved = resolve_labels(
                    item,
                    shot,
                    shot_card=self.shot_cards.get(shot.id),
                    understand_cards=understand.get(shot.media_id) if item else None,
                    peers=self.media,
                )
                if shoot_day is not None:
                    day = resolved["shoot_day"]["value"]
                    media_day = item.shoot_day if item is not None else None
                    if not shoot_days_equal(day, shoot_day) and not shoot_days_equal(media_day, shoot_day):
                        return False
                if role is not None:
                    resolved_ok = roles_equal(resolved["role"]["value"], role)
                    media_ok = item is not None and roles_equal(item.role, role)
                    tag_ok = shot_has_understand_role(shot, str(role).strip().lower())
                    if not resolved_ok and not media_ok and not tag_ok:
                        return False
                return True

            filtered = [shot for shot in filtered if _matches(shot)]
        ordered = sort_shots(filtered, sort, [item.id for item in self.media])
        # Train C: with default capture order, surface understand-tagged spans first.
        if sort is None:
            media_order = {item.id: i for i, item in enumerate(self.media)}
            role_key = str(role).strip().lower() if role is not None else ""

            def _prefer_key(shot: Shot) -> tuple:
                tagged = (
                    shot_has_understand_role(shot, role_key)
                    if role_key
                    else shot_has_any_understand_tag(shot)
                )
                return (0 if tagged else 1, media_order.get(shot.media_id, 10_000), shot.in_s, shot.id)

            ordered = sorted(ordered, key=_prefer_key)
        if limit is not None:
            ordered = ordered[: max(0, int(limit))]
        result = envelope(True, store.timeline, warnings)
        result["shots"] = [shot.model_dump() for shot in ordered]
        return result

    def shots_rank(
        self,
        role: str,
        top_k: int = 5,
        media_id: str | None = None,
        sheet: bool = False,
        shoot_day: int | str | None = None,
    ) -> dict:
        store = self._need()
        if role not in ROLES:
            result = envelope(False, store.timeline, [f"unknown role {role}"])
            result["shots"] = []
            return result
        shots, warnings = self._load_shots(media_id)
        if shoot_day is not None:
            allowed = {
                item.id for item in self.media if shoot_days_equal(item.shoot_day, shoot_day)
            }
            shots = [shot for shot in shots if shot.media_id in allowed]
        kinds = {item.id: item.kind for item in self.media}
        floor_ok = [
            shot
            for shot in shots
            if kinds.get(shot.media_id) != "video" or shot.duration_s + 1e-6 >= SHOT_ACK_MIN_S
        ]
        if floor_ok:
            pool = floor_ok
        else:
            pool = shots
            if shots:
                warnings.append("SPEC-EDIT-ACK-01: no shots meet the acknowledge floor")
        first = self.media[0].id if self.media else None
        sizes = {item.id: (item.width, item.height) for item in self.media}
        media_roles = {item.id: item.role for item in self.media}
        shoot_days = {item.id: item.shoot_day for item in self.media}
        confirmed_roles = confirmed_roles_map(self.media)
        confirmed_shot_roles = confirmed_shot_roles_map(self.shot_cards)
        ranked = rank_shots(
            pool,
            role,
            top_k,
            first_media_id=first,
            sizes=sizes,
            media_roles=media_roles,
            shoot_days=shoot_days,
            confirmed_roles=confirmed_roles,
            confirmed_shot_roles=confirmed_shot_roles,
        )
        result = envelope(True, store.timeline, warnings)
        result["shots"] = [
            {
                **shot.model_dump(),
                "score": round(
                    score_shot(shot, role, first_media_id=first, sizes=sizes),
                    4,
                ),
                "thumb": shot.keyframe,
            }
            for shot in ranked
        ]
        if sheet:
            dest = (store.output_dir / f"rank_{role}.jpg").resolve()
            dest.parent.mkdir(parents=True, exist_ok=True)
            thumbs = [Path(shot.keyframe) for shot in ranked if shot.keyframe]
            contact_sheet(self.runner, thumbs, dest)
            result["path"] = str(dest)
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
        if item.kind == "audio":
            return envelope(False, self._need().timeline, ["SPEC-SND-11: audio files are placed with music_add"])
        is_still = item.kind == "image"
        video_floor = resolved_min_video_duration_s(self._need().project)
        video_target = max(SHOT_ACK_MIN_S, video_floor)
        video_default = min(video_target, item.duration_s or video_target)
        default_dur = DEFAULT_STILL_S if is_still else video_default
        start_in = 0.0 if in_s is None else in_s
        hold_warn: str | None = None
        if out_s is not None:
            end = out_s
            if not is_still and end - 1e-9 > (item.duration_s or 0.0):
                return envelope(
                    False,
                    self._need().timeline,
                    [
                        f"SPEC-EDIT-05: out past source duration "
                        f"(source {item.duration_s:.2f}s, requested out {end:.2f}s)"
                    ],
                )
            dur = round(end - start_in, 4)
        elif duration_s is not None:
            dur = round(float(duration_s), 4)
            end = round(start_in + dur, 4)
            if not is_still:
                avail = max(0.0, (item.duration_s or 0.0) - start_in)
                if dur > avail + 1e-3:
                    hold_warn = (
                        f"SPEC-SND-12: auto-hold last frame "
                        f"({item.duration_s:.2f}s source < {dur:.2f}s requested)"
                    )
        else:
            end = start_in + default_dur
            if not is_still:
                end = min(end, item.duration_s or end)
            dur = round(end - start_in, 4)

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

        result = self._mutate(op_id, apply)
        if hold_warn and result.get("ok"):
            result["warnings"] = [*result.get("warnings", []), hold_warn]
        return result

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
        err = video_floor_reject(clip, source, duration_s, self._need().project)
        if err:
            return envelope(False, self._need().timeline, [err])
        result = self._mutate(op_id, lambda tl: set_duration_clip(tl, clip_id, duration_s, source))
        if result.get("ok"):
            updated = self._clip(clip_id)
            warn = source_hold_warning(updated, source)
            if warn:
                result["warnings"] = [*result.get("warnings", []), warn]
        return result

    def clip_fit(self, clip_id: str, op_id: str | None = None) -> dict:
        clip = self._clip(clip_id)
        source = self._media(clip.media_id)
        return self._mutate(op_id, lambda tl: fit_clip(tl, clip_id, source))

    def clip_set_fit(
        self,
        clip_id: str,
        mode: str,
        pad_color: str | None = None,
        op_id: str | None = None,
    ) -> dict:
        return self._mutate(op_id, lambda tl: set_clip_fit(tl, clip_id, mode, pad_color))

    def clip_refocus(self, clip_id: str, x: float, y: float, op_id: str | None = None) -> dict:
        result = self._mutate(op_id, lambda tl: refocus_clip(tl, clip_id, x, y))
        if not result.get("ok"):
            return result
        try:
            clip = self._clip(clip_id)
        except Reject:
            return result
        hint = self._spatial_hint_for_clip(clip)
        if hint:
            result["focus_hint"] = hint
            warn = spatial_refocus_warning(
                clip_id,
                float(x),
                float(y),
                hint,
                fit=getattr(clip, "fit", None),
            )
            if warn:
                warnings = list(result.get("warnings") or [])
                warnings.append(warn)
                result["warnings"] = warnings
        return result

    def clip_gain(self, clip_id: str, db: float, op_id: str | None = None) -> dict:
        return self._mutate(op_id, lambda tl: gain_clip(tl, clip_id, db))

    def clip_mute(self, clip_id: str, muted: bool = True, op_id: str | None = None) -> dict:
        return self._mutate(op_id, lambda tl: mute_clip(tl, clip_id, muted))

    def layout_list(self) -> dict:
        store = self._need()
        result = envelope(True, store.timeline, [])
        result["layouts"] = [
            {"kind": "stack_v", "panes": 2, "shape": "top/bottom"},
            {"kind": "stack_h", "panes": 2, "shape": "left/right"},
            {"kind": "stack_v3", "panes": 3, "shape": "three rows"},
            {"kind": "grid_2x2", "panes": 4, "shape": "quadrants"},
        ]
        return result

    def layout_add(
        self,
        kind: str,
        panes: list[dict] | str,
        duration_s: float | None = None,
        op_id: str | None = None,
    ) -> dict:
        """Append one layout clip. kind is stack_v, stack_h, stack_v3, or grid_2x2. panes is [{media_id, in_s?, focus_x?, focus_y?}]."""
        try:
            parsed = parse_panes(panes)
            validate_layout(kind, parsed)
            items = [self._media(pane.media_id) for pane in parsed]
            dur = resolve_layout_duration(parsed, items, duration_s)
        except Reject as exc:
            return envelope(False, self._need().timeline, [str(exc)])

        def apply(tl: Timeline) -> Timeline:
            clip = build_layout_clip(new_id("c"), kind, parsed, items, dur)
            return add_layout(tl, clip)

        return self._mutate(op_id, apply)

    def layout_update(
        self,
        clip_id: str,
        kind: str | None = None,
        panes: list[dict] | str | None = None,
        op_id: str | None = None,
    ) -> dict:
        """Change a layout clip's kind or replace its panes."""
        try:
            parsed = parse_panes(panes) if panes is not None else None
            if kind is not None:
                clip = self._clip(clip_id)
                validate_layout(kind, parsed if parsed is not None else clip.panes)
            if parsed is not None:
                for pane in parsed:
                    self._media(pane.media_id)
        except Reject as exc:
            return envelope(False, self._need().timeline, [str(exc)])
        return self._mutate(op_id, lambda tl: update_layout(tl, clip_id, kind=kind, panes=parsed))

    def layout_pane(
        self,
        clip_id: str,
        index: int,
        media_id: str | None = None,
        in_s: float | None = None,
        focus_x: float | None = None,
        focus_y: float | None = None,
        op_id: str | None = None,
    ) -> dict:
        """Edit one pane of a layout clip."""
        clip = self._clip(clip_id)
        if not clip.layout or index < 0 or index >= len(clip.panes):
            return envelope(False, self._need().timeline, [f"SPEC-LAYO-03: pane index {index} is out of range"])
        current = clip.panes[index]
        next_media = media_id or current.media_id
        try:
            self._media(next_media)
            pane = LayoutPane(
                media_id=next_media,
                in_s=current.in_s if in_s is None else in_s,
                focus_x=current.focus_x if focus_x is None else focus_x,
                focus_y=current.focus_y if focus_y is None else focus_y,
            )
            if not (0.0 <= pane.focus_x <= 1.0 and 0.0 <= pane.focus_y <= 1.0):
                raise Reject("SPEC-LAYO-03: focus must be in [0, 1]")
            if pane.in_s < 0:
                raise Reject("SPEC-LAYO-03: in_s must be >= 0")
        except Reject as exc:
            return envelope(False, self._need().timeline, [str(exc)])
        return self._mutate(op_id, lambda tl: set_layout_pane(tl, clip_id, index, pane, clip.duration_s))

    def layout_clear(self, clip_id: str, op_id: str | None = None) -> dict:
        """Turn a layout clip into a full-frame clip of pane 0."""
        return self._mutate(op_id, lambda tl: clear_layout(tl, clip_id))

    def cam_pip(
        self,
        clip_id: str,
        x: float,
        y: float,
        w: float,
        h: float,
        overlay_x: int = 632,
        overlay_y: int = 72,
        overlay_w: int = 420,
        pad: int = 3,
        op_id: str | None = None,
    ) -> dict:
        """Pin a webcam crop from this clip's own 16:9 media as a Reels PiP."""
        clip = self._clip(clip_id)
        media = self._media(clip.media_id)
        if w <= 0 or h <= 0:
            return envelope(False, self._need().timeline, ["SPEC-EDIT-24: crop rect must be positive"])
        src_w, src_h = media.width or 0, media.height or 0
        if src_w > 0 and src_h > 0 and src_h / src_w >= 1.5:
            return envelope(
                False,
                self._need().timeline,
                ["SPEC-EDIT-24: source already fills 9:16; use clip_refocus COVER instead of cam_pip"],
            )
        pip = CamPip(x=x, y=y, w=w, h=h, overlay_x=overlay_x, overlay_y=overlay_y, overlay_w=overlay_w, pad=pad)
        return self._mutate(op_id, lambda tl: set_cam_pip(tl, clip_id, pip))

    def cam_pip_clear(self, clip_id: str, op_id: str | None = None) -> dict:
        self._clip(clip_id)
        return self._mutate(op_id, lambda tl: set_cam_pip(tl, clip_id, None))

    def cam_pip_suggest(self, clip_id: str) -> dict:
        clip = self._clip(clip_id)
        media = self._media(clip.media_id)
        src_w, src_h = media.width or 1920, media.height or 1080
        result = envelope(True, self._need().timeline, [])
        if src_w > 0 and src_h / max(src_w, 1) >= 1.5:
            result["ok"] = False
            result["warnings"] = ["SPEC-EDIT-24: source already fills 9:16"]
            return result
        box_w = min(400, max(160, int(src_w * 0.21)))
        box_h = min(280, max(120, int(src_h * 0.26)))
        result["rect"] = {"x": max(0, src_w - box_w), "y": 0, "w": box_w, "h": box_h}
        return result

    def motion_kenburns(self, clip_id: str, amount: float | None = None, op_id: str | None = None) -> dict:
        return self._mutate(op_id, lambda tl: set_motion(tl, clip_id, "kenburns", amount))

    def motion_punch(self, clip_id: str, op_id: str | None = None) -> dict:
        return self._mutate(op_id, lambda tl: set_motion(tl, clip_id, "punch"))

    def motion_zoom_in(
        self,
        clip_id: str,
        amount: float | None = None,
        frames: int | None = None,
        op_id: str | None = None,
    ) -> dict:
        return self._mutate(op_id, lambda tl: set_motion(tl, clip_id, "zoom_in", amount, frames))

    def motion_zoom_out(
        self,
        clip_id: str,
        amount: float | None = None,
        frames: int | None = None,
        op_id: str | None = None,
    ) -> dict:
        return self._mutate(op_id, lambda tl: set_motion(tl, clip_id, "zoom_out", amount, frames))

    def motion_zoom_pair(
        self,
        clip_id: str,
        amount: float | None = None,
        frames_in: int | None = None,
        frames_out: int | None = None,
        at_s: float | None = None,
        op_id: str | None = None,
    ) -> dict:
        return self._mutate(
            op_id,
            lambda tl: set_zoom_pair(tl, clip_id, amount, frames_in, frames_out, at_s),
        )

    def motion_zoom_suggest(self) -> dict:
        store = self._need()
        suggestions = zoom_suggestions(store.timeline)
        result = envelope(True, store.timeline, [])
        result["suggestions"] = suggestions
        return result

    def motion_none(self, clip_id: str, op_id: str | None = None) -> dict:
        return self._mutate(op_id, lambda tl: set_motion(tl, clip_id, "none"))

    def motion_hold(self, clip_id: str, op_id: str | None = None) -> dict:
        return self._mutate(op_id, lambda tl: set_motion(tl, clip_id, "hold"))

    def motion_speed(self, clip_id: str, rate: float, op_id: str | None = None) -> dict:
        return self._mutate(op_id, lambda tl: set_speed(tl, clip_id, rate))

    def transition_set(
        self,
        clip_id: str | None = None,
        kind: Annotated[
            Literal[
                "cut",
                "hard",
                "fade",
                "whip",
                "match",
                "punch",
                "close_fade",
                "j_cut",
                "l_cut",
                "flash",
            ],
            Field(
                description=(
                    "Pack kinds: cut (default/clear), fade (luma crossfade), whip, match. "
                    "Legacy: hard, punch, close_fade, j_cut, l_cut, flash."
                )
            ),
        ] = "cut",
        from_id: str | None = None,
        from_clip_id: str | None = None,
        at_s: float | None = None,
        duration_s: float | None = None,
        op_id: str | None = None,
    ) -> dict:
        """Set the transition leaving a clip. Prefer section boundaries only (not every cut)."""
        target = clip_id or from_clip_id or from_id
        if target is None and at_s is not None:
            try:
                target = clip_id_for_transition_at(self._need().timeline, float(at_s))
            except Reject as exc:
                return envelope(False, self._need().timeline, [str(exc)])
        if not target:
            return envelope(
                False,
                self._need().timeline,
                ["SPEC-EDIT-13: from_clip_id, clip_id, from_id, or at_s required"],
            )
        if banned_transition(kind):
            return envelope(False, self._need().timeline, ["SPEC-EDIT-13: illegal transition"])
        return self._mutate(
            op_id,
            lambda tl: set_transition(tl, target, kind, duration_s=duration_s),
        )

    def transition_audio_xfade(self, ms: float = 10.0, op_id: str | None = None) -> dict:
        return self._mutate(op_id, lambda tl: set_audio_xfade(tl, ms))

    def fx_grain(self, amount: float, op_id: str | None = None) -> dict:
        return self.adjustment_set(grain=amount, op_id=op_id)

    def fx_vignette(self, amount: float, op_id: str | None = None) -> dict:
        return self.adjustment_set(vignette=amount, op_id=op_id)

    def fx_wrap(self, clip_id: str, mode: str = "off", op_id: str | None = None) -> dict:
        return self._mutate(op_id, lambda tl: set_wrap(tl, clip_id, mode))

    def clip_blur_add(
        self,
        clip_id: str,
        kind: Annotated[
            Literal["face", "plate", "region"],
            Field(description="Privacy blur kind: face, plate, or region."),
        ] = "region",
        x: float | None = None,
        y: float | None = None,
        w: float | None = None,
        h: float | None = None,
        strength: float | None = None,
        feather: float | None = None,
        op_id: str | None = None,
    ) -> dict:
        """Add a soft-mask face / plate / region blur on one clip (post-fit canvas box)."""
        store = self._need()
        clip = self._clip(clip_id)
        warnings: list[str] = []
        try:
            resolved_kind = validate_blur_kind(kind)
            sigma = validate_blur_strength(strength)
            soft = validate_blur_feather(feather)
            box_given = None not in (x, y, w, h)
            if resolved_kind == "region" and not box_given:
                raise Reject("SPEC-FX-11: kind=region requires box x,y,w,h (0-1 of post-fit frame)")
            if box_given:
                box = validate_blur_box(x, y, w, h)  # type: ignore[arg-type]
            else:
                box = self._detect_blur_box(clip, resolved_kind)
                if box is None:
                    result = envelope(True, store.timeline, [f"SPEC-FX-11: no {resolved_kind} found; no blur applied"])
                    result["blur_id"] = None
                    return result
        except Reject as exc:
            return envelope(False, store.timeline, [str(exc)])
        blur = ClipBlur(
            id=new_id("blur"),
            kind=resolved_kind,  # type: ignore[arg-type]
            x=box[0],
            y=box[1],
            w=box[2],
            h=box[3],
            strength=sigma,
            feather=soft,
        )
        if not box_given:
            warnings.append(f"SPEC-FX-11: auto {resolved_kind} box from local detector")
        result = self._mutate(op_id, lambda tl: add_blur(tl, clip_id, blur))
        if result.get("ok"):
            result["blur_id"] = blur.id
            result["blur"] = {**blur.model_dump(), "clip_id": clip_id}
            result["warnings"] = [*result.get("warnings", []), *warnings]
        return result

    def clip_blur_update(
        self,
        blur_id: str,
        x: float | None = None,
        y: float | None = None,
        w: float | None = None,
        h: float | None = None,
        strength: float | None = None,
        feather: float | None = None,
        op_id: str | None = None,
    ) -> dict:
        """Move or retune an existing soft-mask blur."""
        return self._mutate(
            op_id,
            lambda tl: update_blur(tl, blur_id, x=x, y=y, w=w, h=h, strength=strength, feather=feather),
        )

    def clip_blur_remove(self, blur_id: str, op_id: str | None = None) -> dict:
        return self._mutate(op_id, lambda tl: remove_blur(tl, blur_id))

    def clip_blur_list(self, clip_id: str | None = None) -> dict:
        store = self._need()
        try:
            rows = list_blurs(store.timeline, clip_id)
        except Reject as exc:
            return envelope(False, store.timeline, [str(exc)])
        result = envelope(True, store.timeline, [])
        result["blurs"] = rows
        return result

    def _detect_blur_box(self, clip: Clip, kind: str) -> tuple[float, float, float, float] | None:
        store = self._need()
        media = self._media(clip.media_id)
        fresh, _ = ensure_source_proxy(self.runner, store, media)
        self.media = [fresh if m.id == media.id else m for m in self.media]
        ff = "ffmpeg" if isinstance(self.runner, FakeRunner) else find_tool("ffmpeg")
        dest = store.stills_dir / f"{clip.id}_{kind}_detect.jpg"
        dest.parent.mkdir(parents=True, exist_ok=True)
        src = fresh.proxy_path or fresh.path
        seek = None if fresh.kind == "image" else round(clip.in_s + max(0.0, clip.duration_s) * 0.5, 3)
        self.runner.run(
            extract_frame_args(ff, src, dest, kind=fresh.kind, seek_s=seek, scale=None)
        )
        if not dest.exists() or dest.stat().st_size < 32:
            return None
        return detect_box(dest, kind)

    # --- captions ---

    def caption_add(
        self,
        clip_id: str,
        text: str,
        role: str = "body",
        y_pct: float = CAPTION_Y_DEFAULT,
        box: bool = False,
        background: str | None = None,
        banner: bool = False,
        scrim: bool = False,
        enter: str | None = None,
        style: str = "phrase",
        font: str | None = None,
        words: list | None = None,
        op_id: str | None = None,
    ) -> dict:
        store = self._need()
        clip = self._clip(clip_id)
        resolved_style = style if style in ("phrase", "card", "karaoke", "pop") else "phrase"
        parsed_words = _caption_words(words)
        if is_spoken_style(resolved_style) and not parsed_words:
            spec = "SPEC-CAP-10" if resolved_style == "karaoke" else "SPEC-CAP-11"
            return envelope(False, store.timeline, [f"{spec}: {resolved_style} needs word timings"])
        if resolved_style == "pop":
            parsed_words = expand_contractions(parsed_words)
            if not text.strip():
                text = " ".join(w.text for w in parsed_words)
        resolved_role = role if role in ("title", "body") else "body"
        if is_spoken_style(resolved_style):
            resolved_role = "title"
        resolved_enter = enter if enter in ("none", "fade", "punch") else ("punch" if resolved_role == "title" else "fade")
        if is_spoken_style(resolved_style):
            resolved_enter = "none"
        if font:
            resolved_font = normalize_font(font)
            if not resolved_font:
                return envelope(False, store.timeline, [f"unknown font {font}; use {FONT_ALIAS_HELP}"])
        else:
            project_font = store.project.caption_font if store.project else ""
            resolved_font = normalize_font(project_font) if is_card_style(resolved_style) else ""
            if not resolved_font and resolved_style == "card":
                resolved_font = "clash"
        probe_cap = Caption(
            id="tmp",
            clip_id=clip_id,
            text=text,
            role=resolved_role,  # type: ignore[arg-type]
            y_pct=y_pct,
            style=resolved_style,  # type: ignore[arg-type]
            font=resolved_font,
            words=parsed_words,
        )
        issues = caption_issues(
            text,
            y_pct=y_pct,
            clip=clip,
            box=box or bool(background) or banner or scrim,
            role=resolved_role,
            caption=probe_cap,
        )
        if issues:
            return envelope(False, store.timeline, issues)
        lines = wrap_text(text) if resolved_style != "pop" else [text]
        hold = hold_s(text, lines)
        if resolved_style == "pop" and parsed_words:
            hold = round(max(w.end_s for w in parsed_words), 2)
        elif parsed_words:
            hold = max(hold, round(parsed_words[-1].end_s, 2))

        def apply(tl: Timeline) -> Timeline:
            cid = new_id("t")
            numbered = [
                w.model_copy(update={"id": w.id or f"{cid}_w{i}"}) for i, w in enumerate(parsed_words)
            ]
            cap = Caption(
                id=cid,
                clip_id=clip_id,
                text=text,
                role=resolved_role,
                y_pct=y_pct,
                lines=lines,
                hold_s=hold,
                enter=resolved_enter,
                style=resolved_style,
                font=resolved_font,
                words=numbered,
            )
            return tl.model_copy(update={"captions": [*tl.captions, cap]})

        return self._mutate(op_id, apply)

    def caption_edit(
        self,
        caption_id: str,
        text: str | None = None,
        y_pct: float | None = None,
        box: bool = False,
        font: str | None = None,
        op_id: str | None = None,
    ) -> dict:
        store = self._need()
        cap = next((c for c in store.timeline.captions if c.id == caption_id), None)
        if cap is None:
            return envelope(False, store.timeline, [f"unknown caption {caption_id}"])
        new_text = cap.text if text is None else text
        new_y = cap.y_pct if y_pct is None else y_pct
        if font is None:
            new_font = cap.font
        else:
            if font == "":
                new_font = ""
            else:
                new_font = normalize_font(font)
                if not new_font:
                    return envelope(False, store.timeline, [f"unknown font {font}; use {FONT_ALIAS_HELP}"])
        clip = self._clip(cap.clip_id)
        probe = cap.model_copy(update={"text": new_text, "y_pct": new_y, "font": new_font})
        issues = caption_issues(new_text, y_pct=new_y, clip=clip, box=box, caption=probe)
        if issues:
            return envelope(False, store.timeline, issues)
        lines = wrap_text(new_text) if cap.style != "pop" else [new_text]
        hold = cap.hold_s if cap.style == "pop" else hold_s(new_text, lines)

        def apply(tl: Timeline) -> Timeline:
            caps = []
            for c in tl.captions:
                if c.id == caption_id:
                    caps.append(
                        c.model_copy(
                            update={"text": new_text, "y_pct": new_y, "lines": lines, "hold_s": hold, "font": new_font}
                        )
                    )
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
        issues = caption_issues(cap.text, y_pct=new_y, clip=clip, caption=cap)
        if issues:
            return envelope(False, store.timeline, issues)

        def apply(tl: Timeline) -> Timeline:
            caps = [c.model_copy(update={"clip_id": new_clip_id, "y_pct": new_y}) if c.id == caption_id else c for c in tl.captions]
            return tl.model_copy(update={"captions": caps})

        return self._mutate(op_id, apply)

    def caption_emphasis(self, word_id: str, kind: str, op_id: str | None = None) -> dict:
        store = self._need()
        if kind not in ("pop", "enlarge", "scream"):
            return envelope(False, store.timeline, ["SPEC-CAP-12: emphasis must be pop, enlarge, or scream"])
        found = False
        for cap in store.timeline.captions:
            if any(w.id == word_id for w in cap.words):
                found = True
                break
        if not found:
            return envelope(False, store.timeline, [f"unknown word {word_id}"])

        def apply(tl: Timeline) -> Timeline:
            caps = []
            for cap in tl.captions:
                words = [
                    w.model_copy(update={"emphasis": kind}) if w.id == word_id else w for w in cap.words
                ]
                caps.append(cap.model_copy(update={"words": words}))
            return tl.model_copy(update={"captions": caps})

        return self._mutate(op_id, apply)

    def caption_remove(self, caption_id: str, op_id: str | None = None) -> dict:
        return self._mutate(
            op_id,
            lambda tl: tl.model_copy(update={"captions": [c for c in tl.captions if c.id != caption_id]}),
        )

    def caption_lint(self) -> dict:
        store = self._need()
        lint_media = self._lint_media()
        hard = timeline_caption_issues(store.timeline, media=lint_media, project=store.project)
        soft = timeline_caption_warnings(store.timeline, media=lint_media, project=store.project)
        errors = list(hard)
        warns = density_warnings(store.timeline, store.project) + style_warnings(store.timeline) + list(soft)
        cards = []
        media_map = {m.id: m for m in lint_media}
        clips = {c.id: c for c in store.timeline.clips}
        proof_path = None
        proof_issues: list[str] = []
        if store.timeline.captions:
            first = store.timeline.captions[0]
            clip = clips.get(first.clip_id)
            item = media_map.get(clip.media_id) if clip else None
            dest = (store.output_dir / "phone_proof.jpg").resolve()
            proof_path, proof_issues = write_phone_proof(dest, first, item.path if item else None)
            if first.style != "pop":
                errors.extend(proof_issues)
            for cap in store.timeline.captions:
                c = clips.get(cap.clip_id)
                cards.append(card_report(cap, c, media_map.get(c.media_id) if c else None))
        ok = len(errors) == 0
        result = envelope(ok, store.timeline, errors + warns)
        result["errors"] = errors
        result["hold_s"] = cards[0]["hold_s"] if cards else None
        result["lines"] = cards[0]["lines"] if cards else []
        result["bbox"] = cards[0]["bbox"] if cards else None
        result["contrast"] = cards[0]["contrast"] if cards else None
        result["cards"] = cards
        if proof_path:
            result["phone_proof"] = str(proof_path)
        return result

    # --- sound ---

    def sfx_list(self) -> dict:
        store = self._need()
        items = list(sfx_manifest())
        user_items = list_user_sfx_items(store.user_sfx_dir)
        user_kinds = {i["kind"] for i in user_items}
        # Imported keys win over bundled entries of the same kind.
        items = [i for i in items if i.get("kind") not in user_kinds]
        items.extend(user_items)
        result = envelope(True, store.timeline, [])
        result["sfx"] = items
        result["attribution"] = str(attribution_path(store.user_sfx_dir))
        return result

    def sfx_import(
        self,
        path: str,
        kind: Annotated[
            Cc0SfxKind,
            Field(description="CC0 kind tag: whoosh, pop, click, swipe, sparkle, cash, success, paper, bubble, button, correct."),
        ],
        source_name: str = "",
        license: Annotated[
            Literal["CC0", "Mixkit", "Pixabay"],
            Field(description="Allowed: CC0, Mixkit, or Pixabay (case-insensitive at import)."),
        ] = "CC0",
        source_url: str = "",
    ) -> dict:
        store = self._need()
        entry, errors = import_user_sfx_file(
            store.user_sfx_dir,
            Path(path),
            kind=kind,
            source_name=source_name,
            license=license,
            source_url=source_url,
        )
        if errors or entry is None:
            return envelope(False, store.timeline, errors or ["SPEC-SND-18: import failed"])
        result = envelope(True, store.timeline, [])
        result["sfx"] = entry
        result["attribution"] = str(attribution_path(store.user_sfx_dir))
        return result

    def sfx_pack_add(
        self,
        path: str,
        kind: Annotated[
            str,
            Field(
                description="CC0 kind tag when path is a single file (whoosh, pop, click, swipe, sparkle, cash, success, paper, bubble, button, correct). Omit for a pack folder."
            ),
        ] = "",
        source_name: str = "",
        license: Annotated[
            Literal["CC0", "Mixkit", "Pixabay"],
            Field(description="Allowed: CC0, Mixkit, or Pixabay (case-insensitive at import)."),
        ] = "CC0",
        source_url: str = "",
    ) -> dict:
        store = self._need()
        imported, errors = import_user_sfx_pack(
            store.user_sfx_dir,
            Path(path),
            kind=kind,
            source_name=source_name,
            license=license,
            source_url=source_url,
        )
        if errors and not imported:
            return envelope(False, store.timeline, errors)
        result = envelope(True, store.timeline, errors)
        result["sfx"] = imported
        result["attribution"] = str(attribution_path(store.user_sfx_dir))
        return result

    def sfx_place(
        self,
        kind: str = "",
        at_s: float = 0.0,
        gain_db: float = -12.0,
        auto: bool = False,
        key: str = "",
        op_id: str | None = None,
    ) -> dict:
        store = self._need()
        place_kind = (kind or key or "").strip()
        if not place_kind:
            return envelope(False, store.timeline, ["SPEC-SND-02: kind or key is required"])
        if place_kind in MUSIC_KINDS or place_kind.startswith("music"):
            return envelope(False, store.timeline, ["SPEC-SND-01: music is rejected"])
        legal = {i["kind"] for i in sfx_manifest()}
        user_path = find_user_sfx(store.user_sfx_dir, place_kind)
        if place_kind not in legal and user_path is None:
            return envelope(False, store.timeline, [f"unknown sfx {place_kind}"])
        if sfx_too_hot(gain_db, store.timeline.bed_gain_db, store.timeline.bed_kind):
            return envelope(False, store.timeline, ["SPEC-SND-05: SFX must be at least 6 dB under the bed"])

        def apply(tl: Timeline) -> Timeline:
            from lc_editor.models import SfxPlacement

            # `key` alone places by imported key; with `kind`, `key` is auto-idempotency only.
            place_key = key if kind else ""
            if place_key and any(s.key == place_key for s in tl.sfx):
                return tl
            sfx = SfxPlacement(
                id=new_id("s"),
                kind=place_kind,
                at_s=at_s,
                gain_db=gain_db,
                auto=auto,
                key=place_key,
            )
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
                if cap.style == "pop":
                    continue
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

    def sfx_zoom_auto(self, op_id: str | None = None) -> dict:
        def apply(tl: Timeline) -> Timeline:
            from lc_editor.models import SfxPlacement

            existing = {s.key for s in tl.sfx}
            extra = []
            for clip in tl.clips:
                if clip.motion not in ("zoom_in", "zoom_out", "zoom_pair"):
                    continue
                in_at = clip.start_s + (clip.zoom_at_s or 0.0)
                key_in = f"swipe:{clip.id}:in"
                if key_in not in existing:
                    extra.append(
                        SfxPlacement(id=new_id("s"), kind="swipe", at_s=in_at, gain_db=-12.0, auto=True, key=key_in)
                    )
                if clip.motion == "zoom_pair":
                    out_at = clip.start_s + clip.duration_s - (clip.zoom_frames_out / FPS)
                    key_out = f"swipe:{clip.id}:out"
                    if key_out not in existing:
                        extra.append(
                            SfxPlacement(id=new_id("s"), kind="swipe", at_s=max(0.0, out_at), gain_db=-16.0, auto=True, key=key_out)
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

    def audio_highpass(self, hz: float = 120.0, op_id: str | None = None) -> dict:
        if hz <= 0:
            return envelope(False, self._need().timeline, ["SPEC-SND-06: highpass hz must be > 0"])
        return self._mutate(op_id, lambda tl: tl.model_copy(update={"highpass_hz": hz}))

    def audio_denoise(self, clip_id: str, profile: str, op_id: str | None = None) -> dict:
        return self._mutate(op_id, lambda tl: set_denoise(tl, clip_id, profile))

    def audio_gate(self, clip_id: str, enabled: bool = True, op_id: str | None = None) -> dict:
        return self._mutate(op_id, lambda tl: set_gate(tl, clip_id, enabled))

    def mix_preview(self) -> dict:
        store = self._need()
        warnings = mix_issues(store.timeline)
        result = envelope(len(warnings) == 0, store.timeline, warnings)
        result.update(mix_preview_payload(store.timeline))
        return result

    # --- look ---

    def grade_set(self, cube_path_str: str, op_id: str | None = None) -> dict:
        return self.adjustment_set(cube_path_str=cube_path_str, op_id=op_id)

    def grade_preset(self, name: str, op_id: str | None = None) -> dict:
        return self.adjustment_set(grade=name, op_id=op_id)

    def adjustment_set(
        self,
        grade: str | None = None,
        cube_path_str: str | None = None,
        grain: float | None = None,
        vignette: float | None = None,
        wrap: str | None = None,
        intensity: float | None = None,
        eq: dict | None = None,
        colorbalance: dict | None = None,
        fade: bool | None = None,
        end_hold_s: float | None = None,
        op_id: str | None = None,
    ) -> dict:
        store = self._need()
        if grain is not None and (grain < 0 or grain > 1):
            return envelope(False, store.timeline, ["SPEC-FX: grain must be 0-1"])
        if vignette is not None and (vignette < 0 or vignette > 1):
            return envelope(False, store.timeline, ["SPEC-FX: vignette must be 0-1"])
        if wrap is not None and wrap not in ("off", "soft"):
            return envelope(False, store.timeline, ["SPEC-ADJ: wrap must be off or soft"])
        if intensity is not None and (intensity < 0 or intensity > 1):
            return envelope(False, store.timeline, ["SPEC-ADJ: intensity must be 0-1"])
        if end_hold_s is not None and end_hold_s < 0:
            return envelope(False, store.timeline, ["SPEC-ADJ: end_hold_s must be >= 0"])
        if grade is not None and grade not in ("motovlog", "winter_trip", "neutral"):
            return envelope(False, store.timeline, ["unknown grade preset"])
        layer = store.project.adjustment.model_copy()
        update: dict = {"enabled": True}
        project_update: dict = {}
        if grade is not None:
            resolved_cube = cube_path_str if cube_path_str is not None else str(cube_path(grade))
            update["grade_preset"] = grade
            update["cube_path"] = resolved_cube
            update["eq"] = None
            update["colorbalance"] = None
            project_update["grade_preset"] = grade
            project_update["cube_path"] = resolved_cube
        elif cube_path_str is not None:
            update["cube_path"] = cube_path_str
            project_update["cube_path"] = cube_path_str
        if grain is not None:
            update["grain"] = grain
            project_update["grain"] = grain
        if vignette is not None:
            update["vignette"] = vignette
            project_update["vignette"] = vignette
        if wrap is not None:
            update["wrap"] = wrap
        if intensity is not None:
            update["intensity"] = intensity
        if eq is not None:
            update["eq"] = eq
        if colorbalance is not None:
            update["colorbalance"] = colorbalance
        if fade is not None:
            update["fade"] = fade
        if end_hold_s is not None:
            update["end_hold_s"] = end_hold_s
        layer = layer.model_copy(update=update)
        project_update["adjustment"] = layer
        store.project = store.project.model_copy(update=project_update)
        store.persist()
        result = envelope(True, store.timeline, [])
        result["adjustment"] = layer.model_dump()
        return result

    def adjustment_clear(self, op_id: str | None = None) -> dict:
        store = self._need()
        layer = AdjustmentLayer(enabled=False)
        store.project = store.project.model_copy(
            update={"adjustment": layer, "grain": 0.0, "vignette": 0.0}
        )
        store.persist()
        result = envelope(True, store.timeline, [])
        result["adjustment"] = layer.model_dump()
        return result

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

    def review_report(self, allow_dense: bool | None = None) -> dict:
        store = self._need()
        errors = review_blockers(
            store.timeline,
            store.project,
            media=self.media,
            allow_dense=allow_dense,
            lint_media=self._lint_media(),
        )
        warns = review_warnings(
            store.timeline,
            store.project,
            media=self.media,
            user_sfx_dir=store.user_sfx_dir,
            understand_spans=self._understand_spans_for_lint(),
            shot_cards=self.shot_cards,
            shots_by_media=self._shots_by_media(),
        )
        # Train D soft cover-focus suggestions from spatial densify cache.
        hints: dict[str, dict] = {}
        for clip in store.timeline.clips:
            hint = self._spatial_hint_for_clip(clip)
            if hint:
                hints[clip.id] = hint
        warns.extend(spatial_cover_warnings(store.timeline.clips, hints))
        dur = timeline_duration(store.timeline)
        density_relaxed, density_reason = resolve_density_allow(store.project, allow_dense)
        ok = len(errors) == 0
        if ok:
            store.project = store.project.model_copy(update={"reviewed_version": store.timeline.version})
            store.persist()
        report = {
            "duration_s": dur,
            "duration_cap_s": resolved_duration_cap_s(store.project),
            "clip_count": len(store.timeline.clips),
            "density_relaxed": density_relaxed,
            "density_reason": density_reason,
            "caption_warnings": [e for e in errors if "SPEC-CAP" in e],
            "mix_warnings": [e for e in errors if "SPEC-SND" in e or "SPEC-CRAFT-06" in e],
            "transition_count": envelope(True, store.timeline, [])["timeline_summary"]["transition_count"],
            "grade": store.project.grade_preset if store.project else None,
            "in_target_length": DURATION_SOFT_MIN_S
            <= dur
            <= resolved_duration_soft_max_s(store.project),
            "errors": errors,
            "warnings": warns,
            "zoom": {
                "pairs": sum(1 for c in store.timeline.clips if c.motion == "zoom_pair"),
                "punches": sum(1 for c in store.timeline.clips if c.motion == "punch"),
                "skipped": [
                    {"id": row["clip_id"], "reason": row["reason"]}
                    for row in zoom_suggestions(store.timeline)
                    if row["action"] == "none"
                ],
            },
        }
        result = envelope(ok, store.timeline, errors + warns)
        result["errors"] = errors
        result["report"] = report
        return result

    def export(
        self,
        op_id: str | None = None,
        wait: bool = True,
        preset: Annotated[
            Literal["reel", "share", "phone"],
            Field(description="reel=1080 hero; share|phone=720 delivery sidecar."),
        ] = "reel",
    ) -> dict:
        store = self._need()
        replay = store.replay(op_id)
        if replay is not None:
            return replay
        kind = (preset or "reel").strip().lower()
        if kind not in {"reel", "share", "phone"}:
            return envelope(False, store.timeline, ["SPEC-EXPORT-10: preset must be reel, share, or phone"])
        if store.project.reviewed_version != store.timeline.version:
            return envelope(False, store.timeline, ["SPEC-EXPORT-03: export requires review_report on the current version"])
        floor_errors = video_duration_floor_errors(store.timeline, store.project, self.media)
        if floor_errors:
            return envelope(False, store.timeline, floor_errors)
        hero = store.output_dir / "reel.mp4"
        proxy = store.output_dir / "reel_proxy.mp4"
        sidecar = store.output_dir / "reel.json"
        share = store.output_dir / "reel_share.mp4"
        if kind in {"share", "phone"}:
            share_args = share_encode_args(share, store.project.width, store.project.height)
            try:
                with hero_export_lock(wait=wait):
                    assemble(
                        self.runner,
                        store,
                        store.project,
                        store.timeline,
                        self.media,
                        share,
                        proxy=False,
                        encode_args=share_args,
                    )
            except HeroExportBusy:
                return envelope(False, store.timeline, ["hero_export_busy"])
            except AssembleError as exc:
                return envelope(False, store.timeline, [str(exc)])
            result = envelope(True, store.timeline, [])
            result["share"] = str(share.resolve())
            result["encode"] = hero_encode_record(share_args)
            if hero.exists():
                result["hero"] = str(hero.resolve())
            if sidecar.exists():
                result["sidecar"] = str(sidecar.resolve())
            if op_id:
                store.ledger[op_id] = result
                store.persist()
            return result
        try:
            with hero_export_lock(wait=wait):
                assemble(self.runner, store, store.project, store.timeline, self.media, hero, proxy=False)
        except HeroExportBusy:
            return envelope(False, store.timeline, ["hero_export_busy"])
        except AssembleError as exc:
            return envelope(False, store.timeline, [str(exc)])
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
                    "fit": clip.fit,
                    "layout": clip.layout,
                    "panes": [pane.model_dump() for pane in clip.panes],
                }
                for clip in store.timeline.clips
            ],
            "captions": [c.model_dump() for c in store.timeline.captions],
            "layers": [layer.model_dump() for layer in store.timeline.layers],
            "sfx": [{"kind": s.kind, "at_s": s.at_s, "gain_db": s.gain_db} for s in store.timeline.sfx],
            "music": [
                {
                    "id": track.id,
                    "media_id": track.media_id,
                    "source_name": track.source_name,
                    "license_note": track.license_note,
                    "gain_db": track.gain_db,
                    "in_s": track.in_s,
                    "duration_s": track.duration_s,
                    "source": media_map.get(track.media_id).original_path if track.media_id in media_map else "",
                }
                for track in store.timeline.music
            ],
            "beat_grid": store.timeline.beat_grid.model_dump() if store.timeline.beat_grid else None,
            "template_id": store.timeline.template_id,
            "encode": hero_encode_record(hero_encode_args(hero, store.project.width, store.project.height)),
        }
        verify = verify_hero_av(self.runner, hero)
        payload["verify"] = verify
        from lc_editor.store import atomic_write

        atomic_write(sidecar, json.dumps(payload, indent=2))
        warnings = [] if verify.get("ok", True) else [verify.get("warning") or "SPEC-SND-12: hero audio failed verification"]
        result = envelope(verify.get("ok", True), store.timeline, warnings)
        result["hero"] = str(hero.resolve())
        result["proxy"] = str(proxy.resolve())
        result["sidecar"] = str(sidecar.resolve())
        result["verify"] = verify
        if op_id:
            store.ledger[op_id] = result
            store.persist()
        return result

    def layer_add(
        self,
        kind: str,
        start_s: float = 0.0,
        duration_s: float = 2.0,
        media_id: str | None = None,
        text: str = "",
        role: str = "body",
        z: int = 10,
        y_pct: float = CAPTION_Y_DEFAULT,
        motion: str = "fade",
        op_id: str | None = None,
    ) -> dict:
        if kind not in ("video", "image", "text"):
            return envelope(False, self._need().timeline, ["SPEC-LAY-01: kind must be video, image, or text"])
        if kind == "text":
            issues = caption_issues(text, y_pct=y_pct, clip=None, box=False, role=role if role in ("title", "body") else "body")
            if any("box" in i.lower() for i in issues):
                return envelope(False, self._need().timeline, issues)
        style = TextStyle(role=role if role in ("title", "body") else "body", motion=motion if motion in ("none", "fade", "pop", "slide", "type_on") else "fade")
        layer = LayerItem(
            id=new_id("ly"),
            kind=kind,  # type: ignore[arg-type]
            z=z,
            start_s=start_s,
            duration_s=duration_s,
            media_id=media_id,
            text=text,
            role=style.role,
            y_pct=y_pct,
            style=style,
        )
        return self._mutate(op_id, lambda tl: add_layer(tl, layer))

    def layer_update(
        self,
        layer_id: str,
        start_s: float | None = None,
        duration_s: float | None = None,
        z: int | None = None,
        text: str | None = None,
        y_pct: float | None = None,
        op_id: str | None = None,
    ) -> dict:
        return self._mutate(op_id, lambda tl: update_layer(tl, layer_id, start_s=start_s, duration_s=duration_s, z=z, text=text, y_pct=y_pct))

    def layer_remove(self, layer_id: str, op_id: str | None = None) -> dict:
        return self._mutate(op_id, lambda tl: remove_layer(tl, layer_id))

    def layer_reorder(self, layer_id: str, z: int, op_id: str | None = None) -> dict:
        return self._mutate(op_id, lambda tl: reorder_layer(tl, layer_id, z))

    def layer_transform(
        self,
        layer_id: str,
        x: float = 0.5,
        y: float = 0.5,
        scale: float = 1.0,
        rotation: float = 0.0,
        opacity: float = 1.0,
        op_id: str | None = None,
    ) -> dict:
        return self._mutate(op_id, lambda tl: set_transform(tl, layer_id, Transform(x=x, y=y, scale=scale, rotation=rotation, opacity=opacity)))

    def layer_keyframe(
        self,
        layer_id: str,
        t_s: float,
        x: float | None = None,
        y: float | None = None,
        scale: float | None = None,
        rotation: float | None = None,
        opacity: float | None = None,
        ease: str = "smoothstep",
        op_id: str | None = None,
    ) -> dict:
        kf = Keyframe(t_s=t_s, x=x, y=y, scale=scale, rotation=rotation, opacity=opacity, ease=ease if ease in ("linear", "smoothstep") else "smoothstep")
        return self._mutate(op_id, lambda tl: add_keyframe(tl, layer_id, kf))

    def effect_add(self, target: str, name: str, params: dict | None = None, op_id: str | None = None) -> dict:
        try:
            kind = "text" if any(layer.id == target and layer.kind == "text" for layer in self._need().timeline.layers) else "clip"
            clean = validate_effect(name, params, kind)
        except Reject as exc:
            return envelope(False, self._need().timeline, [str(exc)])
        effect = EffectInstance(id=new_id("fx"), name=name, params=clean)
        return self._mutate(op_id, lambda tl: add_effect(tl, target, effect))

    def effect_update(self, effect_id: str, params: dict | None = None, enabled: bool | None = None, op_id: str | None = None) -> dict:
        return self._mutate(op_id, lambda tl: update_effect(tl, effect_id, params=params, enabled=enabled))

    def effect_remove(self, effect_id: str, op_id: str | None = None) -> dict:
        return self._mutate(op_id, lambda tl: remove_effect(tl, effect_id))

    def text_style(
        self,
        layer_id: str,
        motion: str = "fade",
        role: str | None = None,
        font: str | None = None,
        op_id: str | None = None,
    ) -> dict:
        if motion not in ("none", "fade", "pop", "slide", "type_on"):
            return envelope(False, self._need().timeline, ["SPEC-CAP-05: unknown text motion"])
        resolved_font = None
        if font is not None:
            if font == "":
                resolved_font = ""
            else:
                resolved_font = normalize_font(font)
                if not resolved_font:
                    return envelope(False, self._need().timeline, [f"unknown font {font}; use {FONT_ALIAS_HELP}"])

        def apply(tl: Timeline) -> Timeline:
            layers = []
            for layer in tl.layers:
                if layer.id != layer_id:
                    layers.append(layer)
                    continue
                patch: dict = {"motion": motion}
                if role in ("title", "body"):
                    patch["role"] = role
                if resolved_font is not None:
                    patch["font"] = resolved_font
                style = layer.style.model_copy(update=patch)
                layers.append(layer.model_copy(update={"style": style, "role": style.role}))
            return tl.model_copy(update={"layers": layers})

        return self._mutate(op_id, apply)

    def template_list(self) -> dict:
        store = self._need()
        result = envelope(True, store.timeline, [])
        result["templates"] = list_templates(store.templates_dir)
        return result

    def template_apply(self, name: str, bindings: dict | None = None, op_id: str | None = None) -> dict:
        store = self._need()
        try:
            data = load_template(name, store.templates_dir)
        except Reject as exc:
            return envelope(False, store.timeline, [str(exc)])
        look = {}
        if data.get("grade") in ("motovlog", "winter_trip", "neutral"):
            self.adjustment_set(grade=data["grade"], grain=data.get("grain"), vignette=data.get("vignette"))

        def apply(tl: Timeline) -> Timeline:
            new_tl, _warns = apply_template(tl, data, bindings)
            return new_tl

        result = self._mutate(op_id, apply)
        return result

    def template_save(self, name: str, op_id: str | None = None) -> dict:
        store = self._need()
        try:
            path = save_template(name, store.timeline, store.templates_dir, look={"grade": store.project.grade_preset if store.project else None})
        except Reject as exc:
            return envelope(False, store.timeline, [str(exc)])
        result = envelope(True, store.timeline, [])
        result["path"] = str(path)
        return result

    def music_add(
        self,
        media_id: str,
        start_s: float = 0.0,
        in_s: float = 0.0,
        duration_s: float | None = None,
        gain_db: float = -8.0,
        fade_in_s: float = 0.4,
        fade_out_s: float = 0.8,
        loop: bool = False,
        duck_natural: bool = True,
        source_name: str = "",
        license_note: str = "",
        op_id: str | None = None,
    ) -> dict:
        store = self._need()
        item = self._media(media_id)
        if item.kind != "audio":
            return envelope(False, store.timeline, ["SPEC-SND-11: media is not audio"])
        dur = duration_s if duration_s is not None else max(0.1, item.duration_s - in_s)
        track = MusicTrack(
            id=new_id("mu"),
            media_id=media_id,
            start_s=start_s,
            in_s=in_s,
            duration_s=dur,
            gain_db=gain_db,
            fade_in_s=fade_in_s,
            fade_out_s=fade_out_s,
            loop=loop,
            duck_natural=duck_natural,
            source_name=source_name or Path(item.original_path).name,
            license_note=license_note,
        )
        return self._mutate(op_id, lambda tl: add_music(tl, track, allow_music=bool(store.project and store.project.allow_music)))

    def music_update(
        self,
        track_id: str,
        start_s: float | None = None,
        in_s: float | None = None,
        duration_s: float | None = None,
        gain_db: float | None = None,
        fade_in_s: float | None = None,
        fade_out_s: float | None = None,
        loop: bool | None = None,
        duck_natural: bool | None = None,
        source_name: str | None = None,
        license_note: str | None = None,
        op_id: str | None = None,
    ) -> dict:
        return self._mutate(
            op_id,
            lambda tl: update_music(
                tl,
                track_id,
                start_s=start_s,
                in_s=in_s,
                duration_s=duration_s,
                gain_db=gain_db,
                fade_in_s=fade_in_s,
                fade_out_s=fade_out_s,
                loop=loop,
                duck_natural=duck_natural,
                source_name=source_name,
                license_note=license_note,
            ),
        )

    def music_remove(self, track_id: str, op_id: str | None = None) -> dict:
        return self._mutate(op_id, lambda tl: remove_music(tl, track_id))

    def music_list(self) -> dict:
        store = self._need()
        result = envelope(True, store.timeline, [])
        result["music"] = [t.model_dump() for t in store.timeline.music]
        result["beat_grid"] = store.timeline.beat_grid.model_dump() if store.timeline.beat_grid else None
        return result

    def beat_analyze(self, media_id: str, op_id: str | None = None) -> dict:
        store = self._need()
        item = self._media(media_id)
        grid = analyze_beats(self.runner, store.beats_dir, media_id, Path(item.path), item.duration_s)
        result = self._mutate(op_id, lambda tl: set_beat_grid(tl, grid))
        result["beat_grid"] = store.timeline.beat_grid.model_dump() if store.timeline.beat_grid else grid.model_dump()
        return result

    def beat_edit(
        self,
        bpm: float | None = None,
        offset_s: float | None = None,
        beats: list[float] | None = None,
        op_id: str | None = None,
    ) -> dict:
        store = self._need()
        current = store.timeline.beat_grid or BeatGrid(media_id=store.timeline.music[0].media_id if store.timeline.music else "manual")
        update = {"source": "manual"}
        if bpm is not None:
            update["bpm"] = bpm
        if offset_s is not None:
            update["offset_s"] = offset_s
        if beats is not None:
            update["beats"] = beats
        grid = current.model_copy(update=update)
        return self._mutate(op_id, lambda tl: set_beat_grid(tl, grid))

    def beat_sync_preview(
        self,
        strength: float = 1.0,
        subdivision: str = "1",
        min_shot_s: float = 0.5,
        max_shot_s: float = 8.0,
        protected_ids: list[str] | None = None,
    ) -> dict:
        store = self._need()
        preview = propose_beat_sync(
            store.timeline,
            strength=strength,
            subdivision=subdivision,
            min_shot_s=min_shot_s,
            max_shot_s=max_shot_s,
            protected_ids=protected_ids,
        )
        result = envelope(preview["ok"], store.timeline, preview.get("warnings") or [])
        result["proposal"] = preview.get("proposal") or []
        result["sfx"] = preview.get("sfx") or []
        return result

    def beat_sync_apply(
        self,
        strength: float = 1.0,
        subdivision: str = "1",
        min_shot_s: float = 0.5,
        max_shot_s: float = 8.0,
        protected_ids: list[str] | None = None,
        op_id: str | None = None,
    ) -> dict:
        store = self._need()
        preview = propose_beat_sync(
            store.timeline,
            strength=strength,
            subdivision=subdivision,
            min_shot_s=min_shot_s,
            max_shot_s=max_shot_s,
            protected_ids=protected_ids,
        )
        return self._mutate(op_id, lambda tl: apply_beat_sync(tl, preview))

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

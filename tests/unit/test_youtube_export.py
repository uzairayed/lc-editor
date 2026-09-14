from __future__ import annotations

import json
from pathlib import Path

from lc_editor.app import Editor
from lc_editor.lint.captions import caption_issues
from lc_editor.lint.review import decorated_transition_issues
from lc_editor.models import Caption, Clip, Project, Timeline, recompute_starts
from lc_editor.render.graph import youtube_encode_args, youtube_encode_legal
from lc_editor.render.runner import FakeRunner
from lc_editor.render.youtube import validate_youtube_metadata, youtube_srt


def youtube_editor(tmp_path: Path, media_file: Path) -> Editor:
    editor = Editor(workspace=tmp_path, runner=FakeRunner())
    created = editor.project_create(
        name="youtube",
        preset="youtube",
        project_dir=str(tmp_path / "youtube"),
    )
    assert created["ok"] is True
    imported = editor.import_file(str(media_file))
    assert imported["ok"] is True
    added = editor.clip_add(media_id=editor.media[0].id, duration_s=5.0)
    assert added["ok"] is True
    return editor


def test_youtube_project_defaults_to_landscape_long_form(tmp_path: Path) -> None:
    editor = Editor(workspace=tmp_path, runner=FakeRunner())
    result = editor.project_create(
        name="youtube",
        preset="youtube",
        project_dir=str(tmp_path / "youtube"),
    )
    assert result["ok"] is True
    project = editor.project_get()["project"]
    assert (project["width"], project["height"]) == (1920, 1080)
    assert project["duration_cap_s"] == 43200
    assert project["min_video_duration_s"] == 2.0
    assert project["loudnorm"] == "speech"
    assert project["allow_music"] is False
    assert editor.project_set(duration_cap_s=3600)["ok"] is True


def test_youtube_encode_profile(tmp_path: Path) -> None:
    args = youtube_encode_args(tmp_path / "youtube.mp4", 3840, 2160, 60)
    assert youtube_encode_legal(args) is True
    assert args[args.index("-s") + 1] == "3840x2160"
    assert args[args.index("-r") + 1] == "60"
    assert args[args.index("-g") + 1] == "30"
    assert args[args.index("-b:a") + 1] == "384k"
    ntsc = youtube_encode_args(tmp_path / "ntsc.mp4", fps=29.97)
    assert ntsc[ntsc.index("-r") + 1] == "30000/1001"


def test_youtube_export_writes_video_manifest_and_srt(
    tmp_path: Path,
    media_file: Path,
) -> None:
    editor = youtube_editor(tmp_path, media_file)
    clip_id = editor.store.timeline.clips[0].id
    assert editor.caption_add(clip_id=clip_id, text="Accessible caption")["ok"] is True
    assert editor.review_report()["ok"] is True
    result = editor.export(
        preset="youtube",
        caption_mode="sidecar",
        youtube_title="A valid title",
    )
    assert result["ok"] is True
    assert Path(result["youtube"]).name == "youtube.mp4"
    assert Path(result["subtitles"]).read_text(encoding="utf-8-sig").startswith("1\n")
    sidecar = json.loads(Path(result["sidecar"]).read_text(encoding="utf-8"))
    assert sidecar["project_preset"] == "youtube"
    assert sidecar["export_preset"] == "youtube"
    assert sidecar["caption_mode"] == "sidecar"
    assert sidecar["metadata"]["audience_selection_required"] is True


def test_youtube_export_rejects_hdr_without_tone_map(
    tmp_path: Path,
    media_file: Path,
) -> None:
    editor = youtube_editor(tmp_path, media_file)
    editor.media[0] = editor.media[0].model_copy(
        update={"color_transfer": "smpte2084", "color_primaries": "bt2020"}
    )
    assert editor.review_report()["ok"] is True
    result = editor.export(preset="youtube")
    assert result["ok"] is False
    assert any("HDR sources" in warning for warning in result["warnings"])


def test_youtube_failed_export_preserves_previous_file(
    tmp_path: Path,
    media_file: Path,
) -> None:
    editor = youtube_editor(tmp_path, media_file)
    assert editor.review_report()["ok"] is True
    previous = editor.store.output_dir / "youtube.mp4"
    previous.write_bytes(b"previous-good-export")
    editor.runner.fail = True
    result = editor.export(preset="youtube")
    assert result["ok"] is False
    assert previous.read_bytes() == b"previous-good-export"


def test_youtube_metadata_and_subtitle_boundaries() -> None:
    errors = validate_youtube_metadata(
        title="x" * 101,
        description="",
        chapters=[
            {"at_s": 1, "title": "Late"},
            {"at_s": 5, "title": "Short"},
        ],
        duration_s=20,
    )
    assert any("title exceeds" in error for error in errors)
    assert any("start at 0:00" in error for error in errors)
    assert any("at least 3" in error for error in errors)
    timeline = recompute_starts(
        Timeline(
            clips=[Clip(id="c", media_id="m", duration_s=5, out_s=5)],
            captions=[Caption(id="cap", clip_id="c", text="Hello", hold_s=1.5)],
        )
    )
    assert "00:00:00,000 --> 00:00:01,500" in youtube_srt(timeline)


def test_youtube_transition_budget_scales_with_duration() -> None:
    clips = [
        Clip(id=f"c{i}", media_id=f"m{i}", duration_s=24, out_s=24)
        for i in range(5)
    ]
    timeline = recompute_starts(
        Timeline(
            clips=clips,
            transitions={clip.id: "fade" for clip in clips[:-1]},
        )
    )
    project = Project(id="p", name="youtube", preset="youtube")
    assert decorated_transition_issues(timeline, project) == []
    assert decorated_transition_issues(timeline) != []


def test_youtube_caption_geometry_accepts_landscape_lower_third() -> None:
    project = Project(
        id="p",
        name="youtube",
        preset="youtube",
        aspect="16:9",
        width=1920,
        height=1080,
    )
    caption = Caption(id="cap", clip_id="c", text="Landscape title", y_pct=0.75)
    assert caption_issues(
        caption.text,
        y_pct=caption.y_pct,
        clip=None,
        caption=caption,
        project=project,
    ) == []

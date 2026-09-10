from __future__ import annotations

from pathlib import Path

from types import SimpleNamespace

from lc_editor.app import Editor
from lc_editor.lint.quality import clip_uses_cover, quality_blockers
from lc_editor.models import Caption, Clip, LayoutPane, MediaItem, Project, SfxPlacement, Timeline
from lc_editor.render.runner import FakeRunner
from tests.conftest import touch_media


def _video_clip(editor: Editor, media_file: Path) -> str:
    editor.import_file(str(media_file))
    editor.clip_add(media_id=editor.media[-1].id, duration_s=5.0)
    return editor.timeline_get()["timeline"]["clips"][-1]["id"]


def test_review_fails_locked_still_over_1_4s(editor: Editor, tmp_path: Path) -> None:
    still = touch_media(tmp_path / "src", "photo", ".jpg")
    editor.import_file(str(still))
    editor.clip_add(media_id=editor.media[-1].id, duration_s=2.5)
    clip = editor.store.timeline.clips[0]
    editor.store.timeline = editor.store.timeline.model_copy(
        update={"clips": [clip.model_copy(update={"motion": "none", "is_still": True, "duration_s": 2.0})]}
    )
    result = editor.review_report()
    assert result["ok"] is False
    assert any("SPEC-CRAFT-05" in w for w in result["warnings"])
    assert editor.store.project.reviewed_version is None


def test_review_fails_caption_safe_zone(editor: Editor, media_file: Path) -> None:
    clip_id = _video_clip(editor, media_file)
    cap = Caption(id="t1", clip_id=clip_id, text="Cafe Imran, Gharo", y_pct=0.8, lines=["Cafe Imran, Gharo"], hold_s=1.5)
    editor.store.timeline = editor.store.timeline.model_copy(update={"captions": [cap]})
    result = editor.review_report()
    assert result["ok"] is False
    assert any("SPEC-CAP-03" in w for w in result["warnings"])


def test_review_fails_hold_too_short(editor: Editor, media_file: Path) -> None:
    editor.import_file(str(media_file))
    editor.clip_add(media_id=editor.media[-1].id, duration_s=1.2)
    clip_id = editor.timeline_get()["timeline"]["clips"][-1]["id"]
    cap = Caption(id="t1", clip_id=clip_id, text="100 km down the N-5", y_pct=0.36, lines=["100 km down the N-5"], hold_s=1.5)
    editor.store.timeline = editor.store.timeline.model_copy(update={"captions": [cap]})
    result = editor.review_report()
    assert result["ok"] is False
    assert any("SPEC-CAP-02" in w for w in result["warnings"])


def test_review_fails_music_without_opt_in(editor: Editor, media_file: Path) -> None:
    from lc_editor.models import MusicTrack

    _video_clip(editor, media_file)
    editor.store.timeline = editor.store.timeline.model_copy(
        update={"music": [MusicTrack(id="mu1", media_id="missing", duration_s=4.0, source_name="track.mp3")]}
    )
    result = editor.review_report()
    assert result["ok"] is False
    assert any("SPEC-CRAFT-01" in w for w in result["warnings"])


def test_review_allows_opt_in_without_track(editor: Editor, media_file: Path) -> None:
    _video_clip(editor, media_file)
    editor.store.project = editor.store.project.model_copy(update={"allow_music": True})
    result = editor.review_report()
    assert result["ok"] is True


def test_review_fails_sfx_above_bed(editor: Editor, media_file: Path) -> None:
    _video_clip(editor, media_file)
    editor.audio_bed("wind", gain_db=-6.0)
    hot = SfxPlacement(id="s1", kind="tick", at_s=0.0, gain_db=-8.0)
    editor.store.timeline = editor.store.timeline.model_copy(update={"sfx": [hot]})
    result = editor.review_report()
    assert result["ok"] is False
    assert any("SPEC-SND-05" in w for w in result["warnings"])


def test_review_fails_over_60s(editor: Editor, media_file: Path) -> None:
    _video_clip(editor, media_file)
    clip = editor.store.timeline.clips[0]
    editor.store.timeline = editor.store.timeline.model_copy(
        update={"clips": [clip.model_copy(update={"duration_s": 61.0})]}
    )
    result = editor.review_report()
    assert result["ok"] is False
    assert any("SPEC-EDIT-14" in w for w in result["warnings"])


def test_review_blocks_sub720_cover_into_1080(tmp_path: Path) -> None:
    runner = FakeRunner(duration_s=5.0, width=512, height=288)
    editor = Editor(workspace=tmp_path, runner=runner)
    editor.project_create(name="reel", project_dir=str(tmp_path / "reel"))
    media = touch_media(tmp_path / "src", "day1")
    editor.import_file(str(media))
    editor.clip_add(media_id=editor.media[-1].id, duration_s=2.4)
    result = editor.review_report()
    assert result["ok"] is False
    assert any("SPEC-QLT-01" in w and "cover-upscales" in w for w in result["warnings"])
    assert any("SPEC-QLT-01" in e for e in result["errors"])
    assert editor.store.project.reviewed_version is None
    exported = editor.export()
    assert exported["ok"] is False


def test_review_warns_sub720_on_small_canvas(tmp_path: Path) -> None:
    runner = FakeRunner(duration_s=5.0, width=512, height=288)
    editor = Editor(workspace=tmp_path, runner=runner)
    editor.project_create(name="reel", project_dir=str(tmp_path / "reel"))
    media = touch_media(tmp_path / "src", "day1")
    editor.import_file(str(media))
    editor.clip_add(media_id=editor.media[-1].id, duration_s=2.4)
    editor.store.project = editor.store.project.model_copy(update={"width": 540, "height": 960})
    result = editor.review_report()
    assert result["ok"] is True
    assert any("SPEC-QLT-01" in w and "below 720" in w for w in result["warnings"])
    assert not any("cover-upscales" in e for e in result["errors"])


def test_layout_pane_sub720_cover_blocks() -> None:
    media = [
        MediaItem(id="m1", path="a.mp4", original_path="a.mp4", width=512, height=288),
        MediaItem(id="m2", path="b.mp4", original_path="b.mp4", width=1920, height=1080),
    ]
    clip = Clip(
        id="c1",
        media_id="m2",
        duration_s=2.4,
        layout="stack_v",
        panes=[LayoutPane(media_id="m1"), LayoutPane(media_id="m2")],
    )
    project = Project(id="p", name="reel")
    errors = quality_blockers(Timeline(clips=[clip]), project, media)
    assert any("SPEC-QLT-01" in e and "512x288" in e for e in errors)


def test_unknown_size_is_not_sub720() -> None:
    media = [MediaItem(id="m1", path="x.mp4", original_path="x.mp4", width=0, height=0)]
    clip = Clip(id="c1", media_id="m1", duration_s=2.4)
    project = Project(id="p", name="reel")
    assert quality_blockers(Timeline(clips=[clip]), project, media) == []


def test_fit_letterbox_does_not_block_sub720(monkeypatch) -> None:
    assert clip_uses_cover(SimpleNamespace()) is True
    assert clip_uses_cover(SimpleNamespace(fit="fit")) is False
    assert clip_uses_cover(SimpleNamespace(fit_mode="letterbox")) is False
    media = MediaItem(id="m1", path="x.mp4", original_path="x.mp4", width=512, height=288)
    project = Project(id="p", name="reel")
    timeline = Timeline(clips=[Clip(id="c1", media_id="m1", duration_s=2.4)])
    assert quality_blockers(timeline, project, [media])
    monkeypatch.setattr("lc_editor.lint.quality.clip_uses_cover", lambda _clip: False)
    assert quality_blockers(timeline, project, [media]) == []


def test_review_warns_missing_captured_at_not_error(editor: Editor, media_file: Path) -> None:
    editor.import_file(str(media_file))
    editor.clip_add(media_id=editor.media[-1].id, duration_s=2.4)
    editor.media[0] = editor.media[0].model_copy(update={"captured_at": None, "captured_at_source": None})
    result = editor.review_report()
    assert result["ok"] is True
    assert "media missing captured_at" in result["report"]["warnings"]
    assert "media missing captured_at" not in result["report"]["errors"]
    assert result["report"]["errors"] == []


def test_review_ok_unlocks_export(editor: Editor, media_file: Path) -> None:
    _video_clip(editor, media_file)
    review = editor.review_report()
    assert review["ok"] is True
    assert review["report"]["errors"] == []
    exported = editor.export()
    assert exported["ok"] is True
    sidecar = Path(exported["sidecar"])
    assert sidecar.exists()
    data = sidecar.read_text(encoding="utf-8")
    assert "shots" in data
    assert "duration_s" in data
    assert "grade" in data
    replay = editor.export(op_id="exp-side")
    again = editor.export(op_id="exp-side")
    assert replay["sidecar"] == again["sidecar"]

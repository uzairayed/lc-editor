from __future__ import annotations

from pathlib import Path

from lc_editor.app import Editor
from lc_editor.models import Caption, Clip, MediaItem, Project
from lc_editor.render.graph import adjustment_filters, clip_hash_payload, clip_video_filters


def _add(editor: Editor, media_file: Path, duration_s: float = 2.0) -> str:
    editor.import_file(str(media_file))
    editor.clip_add(media_id=editor.media[-1].id, duration_s=duration_s)
    return editor.timeline_get()["timeline"]["clips"][-1]["id"]


def _concat_calls(calls: list[list[str]]) -> list[list[str]]:
    found = []
    for args in calls:
        if "-f" in args and args[args.index("-f") + 1] == "concat":
            found.append(args)
    return found


def _clip_cache_calls(calls: list[list[str]]) -> list[list[str]]:
    return [args for args in calls if any("/clips/" in a.replace("\\", "/") for a in args)]


def test_adjustment_set_and_clear(editor: Editor) -> None:
    set_ok = editor.adjustment_set(grade="motovlog", grain=0.2, vignette=0.3, wrap="soft", intensity=0.7)
    assert set_ok["ok"] is True
    layer = editor.project_get()["project"]["adjustment"]
    assert layer["enabled"] is True
    assert layer["grade_preset"] == "motovlog"
    assert layer["grain"] == 0.2
    assert layer["vignette"] == 0.3
    assert layer["wrap"] == "soft"
    assert layer["intensity"] == 0.7
    assert editor.project_get()["project"]["grade_preset"] == "motovlog"
    assert editor.project_get()["project"]["grain"] == 0.2
    cleared = editor.adjustment_clear()
    assert cleared["ok"] is True
    assert editor.project_get()["project"]["adjustment"]["enabled"] is False
    assert editor.project_get()["project"]["grain"] == 0.0


def test_adjustment_rejects_bad_values(editor: Editor) -> None:
    assert editor.adjustment_set(grain=1.5)["ok"] is False
    assert editor.adjustment_set(wrap="bloom")["ok"] is False
    assert editor.adjustment_set(grade="neon")["ok"] is False
    assert editor.adjustment_set(end_hold_s=-1)["ok"] is False


def test_adjustment_set_does_not_close_export_gate(editor: Editor, media_file: Path) -> None:
    _add(editor, media_file)
    review = editor.review_report()
    assert review["ok"] is True
    version = editor.timeline_get()["timeline_summary"]["version"]
    editor.adjustment_set(grade="winter_trip", grain=0.15)
    assert editor.timeline_get()["timeline_summary"]["version"] == version
    assert editor.export()["ok"] is True


def test_soft_duration_warnings_unchanged(editor: Editor, media_file: Path) -> None:
    _add(editor, media_file, duration_s=2.0)
    editor.adjustment_set(grade="motovlog")
    again = editor.clip_add(media_id=editor.media[-1].id, duration_s=2.0)
    assert again["ok"] is True
    assert any("SPEC-EDIT-15" in w for w in again["warnings"])


def test_clip_filters_stay_local() -> None:
    clip = Clip(id="c1", media_id="m1", motion="punch", wrap="soft")
    media = MediaItem(id="m1", path="x.mp4", original_path="x.mp4", width=1920, height=1080)
    project = Project(id="p", name="n", grade_preset="motovlog", grain=0.4, vignette=0.2, cube_path="look.cube")
    cap = Caption(id="t1", clip_id="c1", text="Cafe Imran", textfile="c.txt")
    filt = clip_video_filters(clip, media, [cap], project, transition="punch")
    assert "lut3d" not in filt
    assert "noise=" not in filt
    assert "vignette=" not in filt
    assert "afftdn" not in filt
    assert "unsharp=" in filt
    assert "textfile=" in filt
    look = Project(
        id="p",
        name="n",
        grade_preset="motovlog",
        cube_path="look.cube",
        grain=0.4,
        vignette=0.2,
    )
    layer = adjustment_filters(look, duration_s=4.0)
    assert "lut3d" in layer
    assert "noise=" in layer
    assert "vignette=" in layer
    assert "afftdn" not in layer
    assert "drawtext" not in layer


def test_eq_overrides_lut() -> None:
    project = Project(id="p", name="n", cube_path="look.cube")
    project = project.model_copy(
        update={
            "adjustment": project.adjustment.model_copy(
                update={"eq": {"saturation": 1.3}, "colorbalance": {"rs": 0.05, "bs": -0.08}}
            )
        }
    )
    filt = adjustment_filters(project)
    assert "eq=saturation=1.3" in filt
    assert "colorbalance=" in filt
    assert "rs=0.05" in filt
    assert "lut3d" not in filt


def test_adjustment_clear_drops_look_filters() -> None:
    project = Project(id="p", name="n", cube_path="look.cube", grain=0.2)
    project = project.model_copy(update={"adjustment": project.adjustment.model_copy(update={"enabled": False})})
    assert adjustment_filters(project) == ""


def test_look_change_reuses_clip_cache(editor: Editor, media_file: Path) -> None:
    _add(editor, media_file)
    editor.clip_add(media_id=editor.media[-1].id, duration_s=2.0)
    editor.review_report()
    first = editor.export()
    assert first["ok"] is True
    cache = editor.store.clip_cache_dir
    before = {p.name: (p.stat().st_mtime_ns, p.read_bytes()) for p in cache.glob("*.mp4")}
    assert before
    editor.adjustment_set(grade="winter_trip", grain=0.25)
    second = editor.export()
    assert second["ok"] is True
    after = {p.name: (p.stat().st_mtime_ns, p.read_bytes()) for p in cache.glob("*.mp4")}
    assert after == before
    concat = _concat_calls(editor.runner.calls)
    assert any("lut3d" in " ".join(args) or "eq=" in " ".join(args) for args in concat)
    clip_blob = " ".join(" ".join(c) for c in _clip_cache_calls(editor.runner.calls))
    assert "lut3d" not in clip_blob


def test_clip_hash_still_sees_local_edits() -> None:
    project = Project(id="p", name="n")
    base = Clip(id="c1", media_id="m1", in_s=0.0, out_s=2.0, motion="none")
    trimmed = base.model_copy(update={"in_s": 0.5, "out_s": 2.0, "duration_s": 1.5})
    punched = base.model_copy(update={"motion": "punch"})
    assert clip_hash_payload(base, [], project) != clip_hash_payload(trimmed, [], project)
    assert clip_hash_payload(base, [], project) != clip_hash_payload(punched, [], project)
    cap = Caption(id="t1", clip_id="c1", text="Cafe Imran")
    assert clip_hash_payload(base, [], project) != clip_hash_payload(base, [cap], project)


def test_denoise_stays_off_the_layer(editor: Editor, media_file: Path) -> None:
    clip_id = _add(editor, media_file)
    editor.motion_punch(clip_id)
    editor.caption_add(clip_id, "Cafe Imran, Gharo")
    editor.audio_denoise(clip_id, "outdoor")
    editor.adjustment_set(grade="motovlog")
    editor.review_report()
    editor.export()
    clip_blob = " ".join(" ".join(c) for c in _clip_cache_calls(editor.runner.calls))
    concat_blob = " ".join(" ".join(c) for c in _concat_calls(editor.runner.calls))
    assert "afftdn" in clip_blob
    assert "afftdn" not in concat_blob
    assert "lut3d" not in clip_blob
    assert "lut3d" in concat_blob

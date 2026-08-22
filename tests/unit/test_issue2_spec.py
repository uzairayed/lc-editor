from __future__ import annotations

from pathlib import Path

from lc_editor.app import Editor
from lc_editor.models import Clip, Timeline
from lc_editor.render.audio import denoise_chain, mix_graph
from lc_editor.render.motion import kenburns_filter
from lc_editor.render.transitions import transition_video, whip_filter


def _add(editor: Editor, media_file: Path, duration_s: float = 2.0) -> str:
    editor.import_file(str(media_file))
    mid = editor.media[-1].id
    editor.clip_add(media_id=mid, duration_s=duration_s)
    return editor.timeline_get()["timeline"]["clips"][-1]["id"]


def test_spec_snd_10_outdoor_denoise_graph() -> None:
    chain = denoise_chain("outdoor")
    assert "afftdn=nr=12" in chain
    assert "agate=attack=10:release=200" in chain
    assert "highpass=f=120" in chain
    timeline = Timeline(clips=[Clip(id="c1", media_id="m1", denoise="outdoor")])
    graph = mix_graph(timeline)
    assert "afftdn" in graph
    assert "agate" in graph
    assert "alimiter" in graph
    assert "music" not in graph
    assert "cinematic" not in graph
    off = denoise_chain("off")
    assert off == ""


def test_spec_trn_new_kinds_and_cap(editor: Editor, media_file: Path) -> None:
    ids = [_add(editor, media_file) for _ in range(5)]
    assert editor.transition_set(ids[0], "j_cut")["ok"] is True
    assert editor.transition_set(from_id=ids[1], kind="l_cut")["ok"] is True
    assert editor.transition_set(ids[2], "flash")["ok"] is True
    assert editor.transition_set(ids[3], "match")["ok"] is True
    for kind in ("j_cut", "l_cut", "flash", "match"):
        assert kind in editor.timeline_get()["timeline"]["transitions"].values()
        assert "wipe" not in transition_video(kind)
        assert "wiperight" not in transition_video(kind)
    review = editor.review_report()
    assert review["ok"] is False
    assert any("SPEC-EDIT-13" in w for w in review["warnings"])


def test_spec_trn_three_decorated_ok(editor: Editor, media_file: Path) -> None:
    ids = [_add(editor, media_file) for _ in range(4)]
    editor.transition_set(ids[0], "whip")
    editor.transition_set(ids[1], "j_cut")
    editor.transition_set(ids[2], "flash")
    review = editor.review_report()
    assert review["ok"] is True


def test_spec_fx_hold_speed_look(editor: Editor, media_file: Path) -> None:
    clip_id = _add(editor, media_file)
    assert editor.motion_hold(clip_id)["ok"] is True
    assert editor.timeline_get()["timeline"]["clips"][0]["motion"] == "none"
    assert editor.motion_speed(clip_id, 1.1)["ok"] is True
    assert editor.motion_speed(clip_id, 2.0)["ok"] is False
    assert editor.fx_grain(0.2)["ok"] is True
    assert editor.fx_vignette(0.3)["ok"] is True
    assert editor.fx_wrap(clip_id, "soft")["ok"] is True
    assert editor.project_get()["project"]["grain"] == 0.2
    assert editor.timeline_get()["timeline"]["clips"][0]["wrap"] == "soft"
    assert editor.audio_denoise(clip_id, "outdoor")["ok"] is True
    assert editor.audio_gate("all", True)["ok"] is True
    assert editor.transition_audio_xfade(0)["ok"] is True
    assert editor.timeline_get()["timeline"]["audio_xfade_ms"] == 0


def test_spec_fx_speed_rejects_still(editor: Editor, tmp_path: Path) -> None:
    from tests.conftest import touch_media

    still = touch_media(tmp_path / "src", "photo", ".jpg")
    editor.import_file(str(still))
    editor.clip_add(media_id=editor.media[-1].id)
    clip_id = editor.timeline_get()["timeline"]["clips"][-1]["id"]
    bad = editor.motion_speed(clip_id, 0.9)
    assert bad["ok"] is False


def test_spec_snd_10_mix_preview_pre_post(editor: Editor, media_file: Path) -> None:
    _add(editor, media_file)
    editor.audio_bed("wind", gain_db=-6.0)
    editor.audio_denoise("all", "outdoor")
    mix = editor.mix_preview()
    assert mix["pre_peak_dbtp"] >= mix["post_peak_dbtp"]
    assert "wind_band" in mix
    assert mix["wind_band"]["post"]["hz_80_400"] < mix["wind_band"]["pre"]["hz_80_400"]


def test_spec_snd_10_denoise_off_warns(editor: Editor, media_file: Path) -> None:
    clip_id = _add(editor, media_file)
    editor.audio_bed("wind")
    editor.audio_denoise(clip_id, "off")
    review = editor.review_report()
    assert any("SPEC-SND-10" in w for w in review["warnings"])


def test_two_clip_preview_proxy(editor: Editor, media_file: Path) -> None:
    a = _add(editor, media_file)
    _add(editor, media_file)
    editor.transition_set(a, "whip")
    result = editor.preview_proxy()
    assert result["ok"] is True
    path = Path(result["path"])
    assert path.exists()
    assert path.stat().st_size > 0


def test_kenburns_and_whip_lock() -> None:
    kb = kenburns_filter(90)
    assert "pow" in kb
    assert "1+0.06*on" not in kb
    whip = whip_filter()
    assert "wipe" not in whip
    assert "wiperight" not in whip

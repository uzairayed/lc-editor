from __future__ import annotations

import json
from pathlib import Path

from lc_editor.models import Clip, Timeline
from lc_editor.render.audio import denoise_chain, resolve_denoise_profile
from lc_editor.render.jobs import render_clip_intermediate
from tests.conftest import touch_media


def test_auto_denoise_is_indoor_without_wind_bed() -> None:
    clip = Clip(id="c1", media_id="m1", denoise="auto")
    indoor = resolve_denoise_profile(clip, Timeline(bed_kind="none"))
    assert indoor == "indoor"
    room = resolve_denoise_profile(clip, Timeline(bed_kind="room"))
    assert room == "indoor"
    outdoor = resolve_denoise_profile(clip, Timeline(bed_kind="wind"))
    assert outdoor == "outdoor"
    chain = denoise_chain("indoor")
    assert "afftdn=nr=6" in chain
    assert "highpass=f=80" in chain
    assert "agate" not in chain


def test_still_hero_emits_silence_of_clip_duration(editor, tmp_path: Path) -> None:
    still = touch_media(tmp_path / "src", "photo", ".jpg")
    editor.import_file(str(still))
    item = editor.media[0]
    clip = Clip(id="c1", media_id=item.id, duration_s=2.5, is_still=True, muted=True)
    timeline = Timeline(clips=[clip])
    render_clip_intermediate(
        editor.runner, editor.store, editor.store.project, timeline, clip, item, [item], preview=False
    )
    blob = " ".join(editor.runner.calls[-1])
    assert "anullsrc" in blob
    assert "2.5" in blob
    assert "-an" not in editor.runner.calls[-1]


def test_live_hero_pads_and_trims_audio(editor, media_file: Path) -> None:
    editor.import_file(str(media_file))
    item = editor.media[0]
    clip = Clip(id="c1", media_id=item.id, duration_s=3.0, in_s=0.0, out_s=3.0)
    timeline = Timeline(clips=[clip])
    render_clip_intermediate(
        editor.runner, editor.store, editor.store.project, timeline, clip, item, [item], preview=False
    )
    blob = " ".join(editor.runner.calls[-1])
    assert "apad" in blob
    assert "atrim" in blob


def test_preview_clip_stays_muted(editor, tmp_path: Path) -> None:
    still = touch_media(tmp_path / "src", "photo", ".jpg")
    editor.import_file(str(still))
    item = editor.media[0]
    clip = Clip(id="c1", media_id=item.id, duration_s=2.5, is_still=True)
    timeline = Timeline(clips=[clip])
    render_clip_intermediate(
        editor.runner, editor.store, editor.store.project, timeline, clip, item, [item], preview=True
    )
    last = editor.runner.calls[-1]
    assert "-an" in last
    assert "anullsrc" not in " ".join(last)


def test_export_sidecar_has_verify_block(editor, media_file: Path) -> None:
    editor.import_file(str(media_file))
    editor.clip_add(media_id=editor.media[-1].id, duration_s=2.5)
    assert editor.review_report()["ok"] is True
    out = editor.export()
    assert out["ok"] is True
    sidecar = json.loads(Path(out["sidecar"]).read_text(encoding="utf-8"))
    assert "verify" in sidecar
    assert sidecar["verify"]["ok"] is True

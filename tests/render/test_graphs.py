from __future__ import annotations

from pathlib import Path

from lc_editor.models import Caption, Clip, MediaItem, Project
from lc_editor.render.captions import drawtext_filter
from lc_editor.render.graph import clip_hash_payload, clip_video_filters
from lc_editor.render.motion import kenburns_filter, punch_filter, zoom_hit_filter
from lc_editor.render.transitions import close_fade_filter, punch_in_filter, whip_filter


def test_spec_rnd_03_whip_eased_not_wipe() -> None:
    graph = whip_filter()
    assert "wiperight" not in graph
    assert "wipe" not in graph
    assert "xfade" not in graph
    assert "boxblur" in graph
    assert "pow" in graph
    assert "sin(PI" in graph


def test_spec_rnd_01_kenburns_eased() -> None:
    graph = kenburns_filter(60)
    assert "0.06" in graph
    assert "zoompan" in graph
    assert "pow" in graph
    assert "1+0.06*on" not in graph


def test_spec_rnd_02_punch_108_four_frames() -> None:
    graph = punch_filter()
    assert "1.08" in graph or "0.08" in graph
    assert "4" in graph


def test_spec_rnd_19_zoom_hit_twelve_frames() -> None:
    graph = zoom_hit_filter("zoom_in")
    assert "1.14" in graph or "0.14" in graph
    assert "12" in graph
    out = zoom_hit_filter("zoom_out", frames=12, amount=1.14)
    assert "1.14" in out or "0.14" in out
    clip = Clip(id="c1", media_id="m1", motion="zoom_in", duration_s=2.4, zoom_frames=12, zoom_amount=1.14)
    media = MediaItem(id="m1", path="x.mp4", original_path="x.mp4", width=1920, height=1080)
    filt = clip_video_filters(clip, media, [], Project(id="p", name="n"))
    assert "1.14" in filt or "0.14" in filt


def test_spec_rnd_04_close_fade_four_frames() -> None:
    graph = close_fade_filter(90)
    assert graph == "fade=t=out:s=86:n=4"


def test_spec_rnd_06_drawtext_no_box(tmp_path: Path) -> None:
    cap = Caption(id="t1", clip_id="c1", text="Cafe Imran, Gharo", textfile=str(tmp_path / "c.txt"))
    (tmp_path / "c.txt").write_text("Cafe Imran, Gharo", encoding="utf-8")
    filt = drawtext_filter(cap, tmp_path / "c.txt", None)
    assert "textfile=" in filt
    assert "expansion=none" in filt
    assert "0xF6EBD4" in filt
    assert "0x1A1410" in filt
    assert "borderw=3" in filt
    assert "box=1" not in filt
    assert "Cafe Imran" not in filt


def test_spec_rnd_10_hash_ignores_other_clips() -> None:
    project = Project(id="p", name="n")
    clip = Clip(id="c1", media_id="m1")
    a = clip_hash_payload(clip, [Caption(id="t1", clip_id="c1", text="A")], project)
    b = clip_hash_payload(clip, [Caption(id="t1", clip_id="c1", text="A"), Caption(id="t2", clip_id="c2", text="B")], project)
    assert a == b


def test_spec_adj_hash_ignores_look() -> None:
    clip = Clip(id="c1", media_id="m1")
    a = clip_hash_payload(clip, [], Project(id="p", name="n", grade_preset="neutral", grain=0.0))
    b = clip_hash_payload(clip, [], Project(id="p", name="n", grade_preset="motovlog", grain=0.5, vignette=0.3))
    assert a == b


def test_spec_rnd_05_hard_cut_has_no_xfade() -> None:
    clip = Clip(id="c1", media_id="m1")
    media = MediaItem(id="m1", path="x.mp4", original_path="x.mp4", width=1920, height=1080)
    project = Project(id="p", name="n")
    filt = clip_video_filters(clip, media, [], project)
    assert "xfade" not in filt
    assert "wipe" not in filt


def test_spec_rnd_punch_transition_builder() -> None:
    assert "1.08" in punch_in_filter() or "0.079999" in punch_in_filter() or "0.08" in punch_in_filter()

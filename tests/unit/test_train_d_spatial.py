"""Train D: LENS-lite spatial densify + soft focus hints."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

from lc_editor.analysis.manifest import Shot, ShotMetrics, write_manifest
from lc_editor.analysis.spatial import (
    DEFAULT_SPATIAL_BUDGET,
    analyze_keyframe_spatial,
    annotate_span_spatial,
    clamp_spatial_budget,
    is_high_value_span,
    select_spatial_targets,
    spatial_cover_warnings,
    spatial_refocus_warning,
)
from lc_editor.analysis.understand import write_understand_cache
from lc_editor.app import Editor
from lc_editor.models import Clip
from tests.conftest import touch_media


def _shot(media_id: str, index: int, **overrides) -> Shot:
    metrics = overrides.pop("metrics", ShotMetrics())
    in_s = overrides.pop("in_s", float(index) * 2)
    out_s = overrides.pop("out_s", in_s + overrides.pop("length", 2.0))
    data = {
        "id": f"hash_{index:02d}",
        "media_id": media_id,
        "in_s": in_s,
        "out_s": out_s,
        "duration_s": round(out_s - in_s, 4),
        "keyframe": overrides.pop("keyframe", f"/tmp/hash_{index:02d}.jpg"),
        "metrics": metrics,
        "tags": overrides.pop("tags", []),
    }
    data.update(overrides)
    return Shot.model_validate(data)


def _write_busy_frame(path: Path) -> None:
    """Scattered edge blobs → low dominance / high entropy."""
    img = Image.new("L", (180, 180), 8)
    draw = ImageDraw.Draw(img)
    for x, y in (
        (8, 8),
        (150, 12),
        (20, 150),
        (155, 155),
        (85, 20),
        (12, 85),
        (150, 85),
        (85, 150),
        (60, 60),
        (110, 110),
    ):
        draw.rectangle((x, y, x + 10, y + 10), fill=240)
        draw.line((x, y, x + 10, y + 10), fill=255, width=2)
    img.save(path, format="JPEG", quality=95)


def _write_dominant_frame(path: Path) -> None:
    """Tiny sharp subject in one tile only → high concentration, leftward focus."""
    img = Image.new("L", (180, 180), 0)
    draw = ImageDraw.Draw(img)
    # Confine detail to left-middle tile (~0..60 x, 60..120 y).
    for i in range(8):
        x0 = 12 + (i % 3) * 14
        y0 = 72 + (i // 3) * 14
        draw.rectangle((x0, y0, x0 + 10, y0 + 10), fill=255)
        draw.line((x0, y0, x0 + 10, y0 + 10), fill=200, width=2)
    img.save(path, format="JPEG", quality=95)


def test_clamp_spatial_budget() -> None:
    assert clamp_spatial_budget(None) == DEFAULT_SPATIAL_BUDGET
    assert clamp_spatial_budget(1) == 4
    assert clamp_spatial_budget(99) == 32


def test_analyze_keyframe_spatial_dominance(tmp_path: Path) -> None:
    busy = tmp_path / "busy.jpg"
    dominant = tmp_path / "dom.jpg"
    _write_busy_frame(busy)
    _write_dominant_frame(dominant)
    busy_a = analyze_keyframe_spatial(busy)
    dom_a = analyze_keyframe_spatial(dominant)
    assert busy_a["ok"] is True
    assert dom_a["ok"] is True
    assert dom_a["dominance"] > busy_a["dominance"]
    assert busy_a["ambiguous"] is True
    assert dom_a["ambiguous"] is False
    assert dom_a["focus_x"] < 0.45


def test_select_spatial_targets_high_value_ambiguous(tmp_path: Path) -> None:
    busy = tmp_path / "b.jpg"
    quiet = tmp_path / "q.jpg"
    _write_busy_frame(busy)
    _write_dominant_frame(quiet)
    cards = [
        {
            "media_id": "m",
            "in_s": 0.0,
            "out_s": 4.0,
            "score": 0.9,
            "keyframe_path": str(busy),
            "role_hint": "wash",
        },
        {
            "media_id": "m",
            "in_s": 4.0,
            "out_s": 8.0,
            "score": 0.1,
            "keyframe_path": str(busy),
            "role_hint": "before",
        },
        {
            "media_id": "m",
            "in_s": 8.0,
            "out_s": 12.0,
            "score": 0.85,
            "keyframe_path": str(quiet),
            "role_hint": "after",
        },
    ]
    assert is_high_value_span(cards[0], cards)
    assert not is_high_value_span(cards[1], cards)
    targets = select_spatial_targets(cards)
    assert len(targets) == 1
    assert targets[0]["in_s"] == 0.0
    assert targets[0]["spatial_ambiguous"] is True
    assert "focus_hint" in targets[0]


def test_spatial_refocus_warning_soft_only() -> None:
    hint = {"focus_x": 0.2, "focus_y": 0.4, "confidence": 0.7}
    msg = spatial_refocus_warning("c1", 0.5, 0.5, hint, fit="cover")
    assert msg is not None
    assert "SPEC-ANA-15" in msg
    assert "soft suggestion" in msg
    assert spatial_refocus_warning("c1", 0.5, 0.5, hint, fit="fit") is None
    assert spatial_refocus_warning("c1", 0.22, 0.41, hint, fit="cover") is None
    clip = Clip(id="c1", media_id="m", in_s=0.0, out_s=2.0, focus_x=0.5, focus_y=0.5)
    warns = spatial_cover_warnings([clip], {"c1": hint})
    assert any("SPEC-ANA-15" in w for w in warns)


def test_media_understand_spatial_densifies(editor: Editor, tmp_path: Path) -> None:
    media = touch_media(tmp_path / "src", "spatial")
    editor.import_file(str(media))
    mid = editor.media[0].id
    busy = editor.store.keyframes_dir / "busy.jpg"
    _write_busy_frame(busy)
    shots = [
        _shot(
            mid,
            0,
            metrics=ShotMetrics(motion=0.7, sharpness=0.5, audio_class="ambient"),
            keyframe=str(busy),
            length=8.0,
        ),
    ]
    write_manifest(editor._manifest_for(editor.media[0]), shots)
    write_understand_cache(
        editor._understand_for(editor.media[0]),
        {
            "media_id": mid,
            "query_roles": ["wash", "after"],
            "cards": [
                {
                    "media_id": mid,
                    "in_s": 0.0,
                    "out_s": 8.0,
                    "role_hint": "wash",
                    "score": 0.88,
                    "keyframe_path": str(busy),
                    "reason": "seed",
                    "role_scores": {"wash": 0.88},
                }
            ],
        },
    )
    version = editor.timeline_get()["timeline_summary"]["version"]
    before = len(editor.runner.calls)
    result = editor.media_understand_spatial(media_id=mid, budget_frames=6)
    assert result["ok"] is True
    assert result["timeline_summary"]["version"] == version
    assert result["selection"] == "spatial"
    assert result["spans"]
    card = result["spans"][0]
    assert "focus_hint" in card
    assert "focus_x" in card["focus_hint"]
    assert "focus_y" in card["focus_hint"]
    assert card.get("spatial_densified") is True
    cached = editor._understand_for(editor.media[0])
    assert cached.exists()
    joined = " ".join(" ".join(c) for c in editor.runner.calls[before:])
    assert "scdet" not in joined


def test_media_understand_refine_spatial_flag(editor: Editor, tmp_path: Path) -> None:
    media = touch_media(tmp_path / "src", "refine_spatial")
    editor.import_file(str(media))
    mid = editor.media[0].id
    kf = editor.store.keyframes_dir / "base.jpg"
    _write_busy_frame(kf)
    shots = [
        _shot(mid, 0, metrics=ShotMetrics(motion=0.2, sharpness=0.5), keyframe=str(kf), length=8.0),
    ]
    write_manifest(editor._manifest_for(editor.media[0]), shots)
    plain = editor.media_understand_refine(mid, 1.0, 5.0, budget_frames=4)
    assert plain["ok"] is True
    assert plain.get("spatial") is False
    assert "focus_hint" not in plain["spans"][0]

    spatial = editor.media_understand_refine(mid, 1.0, 5.0, budget_frames=4, spatial=True)
    assert spatial["ok"] is True
    assert spatial["spatial"] is True
    assert spatial["selection"] == "refine_spatial"
    assert "focus_hint" in spatial["spans"][0]


def test_clip_refocus_surfaces_spatial_hint(editor: Editor, tmp_path: Path) -> None:
    media = touch_media(tmp_path / "src", "refocus_hint")
    editor.import_file(str(media))
    mid = editor.media[0].id
    busy = editor.store.keyframes_dir / "busy.jpg"
    _write_dominant_frame(busy)
    write_manifest(
        editor._manifest_for(editor.media[0]),
        [_shot(mid, 0, keyframe=str(busy), length=4.0)],
    )
    write_understand_cache(
        editor._understand_for(editor.media[0]),
        {
            "media_id": mid,
            "spatial": {
                "spans": [
                    {
                        "media_id": mid,
                        "in_s": 0.0,
                        "out_s": 4.0,
                        "score": 0.9,
                        "focus_hint": {
                            "focus_x": 0.2,
                            "focus_y": 0.5,
                            "confidence": 0.8,
                            "reason": "test",
                        },
                    }
                ]
            },
        },
    )
    added = editor.clip_add(media_id=mid, in_s=0.0, out_s=2.0)
    assert added["ok"] is True
    clip_id = editor._need().timeline.clips[0].id

    drifted = editor.clip_refocus(clip_id, 0.5, 0.5)
    assert drifted["ok"] is True
    assert "focus_hint" in drifted
    assert any("SPEC-ANA-15" in w for w in (drifted.get("warnings") or []))

    aligned = editor.clip_refocus(clip_id, 0.2, 0.5)
    assert aligned["ok"] is True
    assert not any("SPEC-ANA-15" in w for w in (aligned.get("warnings") or []))

    report = editor.review_report()
    assert not any(
        "SPEC-ANA-15" in w and "soft suggestion" in w for w in (report.get("warnings") or [])
    )


def test_annotate_span_spatial_preserves_role_fields(tmp_path: Path) -> None:
    path = tmp_path / "k.jpg"
    _write_dominant_frame(path)
    card = {
        "media_id": "m",
        "in_s": 1.0,
        "out_s": 3.0,
        "role_hint": "wheel",
        "score": 0.7,
        "keyframe_path": str(path),
        "reason": "sharp",
        "role_scores": {"wheel": 0.7},
    }
    out = annotate_span_spatial(card)
    assert out["role_hint"] == "wheel"
    assert out["role_scores"] == {"wheel": 0.7}
    assert "focus_hint" in out

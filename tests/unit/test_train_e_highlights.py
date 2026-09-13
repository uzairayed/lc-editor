"""Train E: highlights_suggest arc-first beat sheets from understand spans."""

from __future__ import annotations

from pathlib import Path

from lc_editor.analysis.highlights import (
    DEFAULT_TARGET_PROCESS_S,
    DEFAULT_TARGET_REEL_S,
    build_candidate_sheet,
    clamp_target_s,
    normalize_style,
    section_for_role,
    suggest_highlight_sheets,
)
from lc_editor.analysis.manifest import Shot, ShotMetrics, write_manifest
from lc_editor.analysis.understand import write_understand_cache
from lc_editor.app import Editor
from tests.conftest import touch_media


def _shot(media_id: str, index: int, **overrides) -> Shot:
    metrics = overrides.pop("metrics", ShotMetrics())
    in_s = overrides.pop("in_s", float(index) * 8)
    out_s = overrides.pop("out_s", in_s + overrides.pop("length", 8.0))
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


def _card(
    media_id: str,
    role: str,
    *,
    in_s: float,
    out_s: float,
    score: float,
    reason: str | None = None,
    focus_hint: dict | None = None,
    captured_at: str | None = None,
    shoot_day: int | None = None,
) -> dict:
    card = {
        "media_id": media_id,
        "in_s": in_s,
        "out_s": out_s,
        "role_hint": role,
        "score": score,
        "keyframe_path": f"/tmp/{role}.jpg",
        "reason": reason or f"{role} span",
        "role_scores": {role: score},
        "source": "understand",
        "captured_at": captured_at,
        "shoot_day": shoot_day,
    }
    if focus_hint:
        card["focus_hint"] = focus_hint
    return card


def test_normalize_style_and_target() -> None:
    assert normalize_style("PROCESS") == "process"
    assert normalize_style("nope") == "process"
    assert normalize_style("reel") == "reel"
    assert clamp_target_s(None, "process") == DEFAULT_TARGET_PROCESS_S
    assert clamp_target_s(None, "reel") == DEFAULT_TARGET_REEL_S
    assert clamp_target_s(3.0, "process") == 8.0
    assert clamp_target_s(999.0, "process") == 180.0


def test_section_for_role_process_arc() -> None:
    assert section_for_role("before") == "before"
    assert section_for_role("wash") == "process"
    assert section_for_role("machine") == "process"
    assert section_for_role("polish") == "after"
    assert section_for_role("after") == "after"
    assert section_for_role("hero") == "hero"


def test_build_candidate_prefers_transformation_arc() -> None:
    cards = [
        _card("m", "after", in_s=40, out_s=48, score=0.95),
        _card("m", "before", in_s=0, out_s=8, score=0.7),
        _card("m", "wash", in_s=8, out_s=16, score=0.8),
        _card("m", "machine", in_s=16, out_s=24, score=0.85),
        _card("m", "wheel", in_s=24, out_s=32, score=0.75),
    ]
    sheet = build_candidate_sheet(cards, target_s=45.0, style="process", process_count=3)
    assert sheet is not None
    roles = [b["role"] for b in sheet["beats"]]
    assert roles[0] == "before"
    assert roles[-1] == "after"
    assert "wash" in roles or "machine" in roles or "wheel" in roles
    assert sheet["arc_complete"] is True
    assert "transformation" in sheet["reason"].lower()
    # Packed toward target; source spans (8s each) may cap below target.
    assert sheet["duration_s"] >= 28.0
    assert sheet["duration_s"] <= 45.0 + 1e-6


def test_suggest_ranks_complete_arc_above_incomplete() -> None:
    complete = [
        _card("m", "before", in_s=0, out_s=8, score=0.6),
        _card("m", "wash", in_s=8, out_s=16, score=0.7),
        _card("m", "machine", in_s=16, out_s=24, score=0.7),
        _card("m", "after", in_s=40, out_s=48, score=0.8),
    ]
    thin = [
        _card("m", "wash", in_s=0, out_s=8, score=0.99),
        _card("m", "machine", in_s=8, out_s=16, score=0.99),
    ]
    ranked = suggest_highlight_sheets(complete + thin, target_s=40.0, style="process")
    assert ranked
    assert ranked[0]["arc_complete"] is True
    assert ranked[0]["rank"] == 1
    assert "before" in ranked[0]["arc"]
    assert "after" in ranked[0]["arc"]


def test_process_style_soft_penalizes_speech_not_required() -> None:
    silent = [
        _card("m", "before", in_s=0, out_s=8, score=0.65, reason="dusty/dull still"),
        _card("m", "wash", in_s=8, out_s=16, score=0.7, reason="wet-work motion"),
        _card("m", "after", in_s=40, out_s=48, score=0.75, reason="clean/shiny payoff"),
    ]
    speechy = [
        _card("m", "before", in_s=0, out_s=8, score=0.66, reason="speech peak hook"),
        _card("m", "wash", in_s=8, out_s=16, score=0.71, reason="speech transcript highlight"),
        _card("m", "after", in_s=40, out_s=48, score=0.76, reason="speech closer"),
    ]
    silent_sheet = build_candidate_sheet(silent, target_s=30.0, style="process")
    speech_sheet = build_candidate_sheet(speechy, target_s=30.0, style="process")
    assert silent_sheet and speech_sheet
    assert silent_sheet["score"] >= speech_sheet["score"]


def test_focus_hint_attached_from_spatial_cache() -> None:
    cards = [
        _card("m1", "before", in_s=0, out_s=8, score=0.7),
        _card("m1", "wash", in_s=8, out_s=16, score=0.8),
        _card("m1", "after", in_s=40, out_s=48, score=0.9),
    ]
    spatial = {
        "m1": {
            "spans": [
                {
                    "media_id": "m1",
                    "in_s": 8.0,
                    "out_s": 16.0,
                    "score": 0.8,
                    "focus_hint": {
                        "focus_x": 0.32,
                        "focus_y": 0.55,
                        "confidence": 0.8,
                        "reason": "tile peak",
                    },
                }
            ]
        }
    }
    sheet = build_candidate_sheet(
        cards,
        target_s=30.0,
        style="process",
        process_count=1,
        spatial_by_media=spatial,
    )
    assert sheet is not None
    wash = next(b for b in sheet["beats"] if b["role"] == "wash")
    assert wash["focus_hint"]["focus_x"] == 0.32
    assert wash["focus_hint"]["confidence"] == 0.8


def test_highlights_suggest_from_cache_no_timeline_mutate(editor: Editor, tmp_path: Path) -> None:
    media = touch_media(tmp_path / "src", "arc")
    editor.import_file(str(media))
    mid = editor.media[0].id
    shots = [
        _shot(mid, 0, metrics=ShotMetrics(motion=0.05, sharpness=0.5, luma_mean=0.2), length=8.0),
        _shot(mid, 1, metrics=ShotMetrics(motion=0.7, sharpness=0.4, audio_class="ambient"), length=8.0),
        _shot(mid, 2, metrics=ShotMetrics(motion=0.6, sharpness=0.5, audio_class="engine"), length=8.0),
        _shot(mid, 3, metrics=ShotMetrics(motion=0.05, sharpness=0.9, luma_mean=0.85), length=8.0),
    ]
    for i, shot in enumerate(shots):
        kf = editor.store.keyframes_dir / f"e{i}.jpg"
        kf.write_bytes(b"\xff\xd8\xff\xd9")
        shots[i] = shot.model_copy(update={"keyframe": str(kf)})
    write_manifest(editor._manifest_for(editor.media[0]), shots)
    cards = [
        {
            "media_id": mid,
            "in_s": 0.0,
            "out_s": 8.0,
            "role_hint": "before",
            "score": 0.7,
            "keyframe_path": shots[0].keyframe,
            "reason": "dusty",
            "role_scores": {"before": 0.7},
            "shot_id": shots[0].id,
        },
        {
            "media_id": mid,
            "in_s": 8.0,
            "out_s": 16.0,
            "role_hint": "wash",
            "score": 0.8,
            "keyframe_path": shots[1].keyframe,
            "reason": "wet-work",
            "role_scores": {"wash": 0.8},
            "shot_id": shots[1].id,
        },
        {
            "media_id": mid,
            "in_s": 16.0,
            "out_s": 24.0,
            "role_hint": "machine",
            "score": 0.82,
            "keyframe_path": shots[2].keyframe,
            "reason": "tool work",
            "role_scores": {"machine": 0.82},
            "shot_id": shots[2].id,
        },
        {
            "media_id": mid,
            "in_s": 24.0,
            "out_s": 32.0,
            "role_hint": "after",
            "score": 0.9,
            "keyframe_path": shots[3].keyframe,
            "reason": "payoff",
            "role_scores": {"after": 0.9},
            "shot_id": shots[3].id,
        },
    ]
    write_understand_cache(
        editor._understand_for(editor.media[0]),
        {
            "media_id": mid,
            "query_roles": ["before", "wash", "machine", "after"],
            "cards": cards,
            "spatial": {
                "spans": [
                    {
                        "media_id": mid,
                        "in_s": 8.0,
                        "out_s": 16.0,
                        "score": 0.8,
                        "focus_hint": {
                            "focus_x": 0.4,
                            "focus_y": 0.5,
                            "confidence": 0.7,
                            "reason": "busy wash",
                        },
                    }
                ]
            },
        },
    )
    version = editor.timeline_get()["timeline_summary"]["version"]
    result = editor.highlights_suggest(target_s=40.0, style="process")
    assert result["ok"] is True
    assert result["suggest_only"] is True
    assert result["auto_export"] is False
    assert result["from_cache"] is True
    assert result["style"] == "process"
    assert result["target_s"] == 40.0
    assert result["timeline_summary"]["version"] == version
    assert result["candidates"]
    top = result["candidates"][0]
    assert top["arc_complete"] is True
    assert top["beats"]
    roles = [b["role"] for b in top["beats"]]
    assert roles[0] == "before"
    assert roles[-1] == "after"
    wash = next((b for b in top["beats"] if b["role"] == "wash"), None)
    assert wash is not None
    assert wash.get("focus_hint", {}).get("focus_x") == 0.4


def test_highlights_suggest_reel_style(editor: Editor, tmp_path: Path) -> None:
    media = touch_media(tmp_path / "src", "reel")
    editor.import_file(str(media))
    mid = editor.media[0].id
    shots = [
        _shot(mid, 0, metrics=ShotMetrics(motion=0.05, sharpness=0.5, luma_mean=0.25), length=6.0),
        _shot(mid, 1, metrics=ShotMetrics(motion=0.6, sharpness=0.5), length=6.0),
        _shot(mid, 2, metrics=ShotMetrics(motion=0.05, sharpness=0.9, luma_mean=0.85), length=6.0),
    ]
    for i, shot in enumerate(shots):
        kf = editor.store.keyframes_dir / f"r{i}.jpg"
        kf.write_bytes(b"\xff\xd8\xff\xd9")
        shots[i] = shot.model_copy(update={"keyframe": str(kf)})
    write_manifest(editor._manifest_for(editor.media[0]), shots)
    write_understand_cache(
        editor._understand_for(editor.media[0]),
        {
            "media_id": mid,
            "cards": [
                {
                    "media_id": mid,
                    "in_s": 0.0,
                    "out_s": 6.0,
                    "role_hint": "before",
                    "score": 0.7,
                    "keyframe_path": shots[0].keyframe,
                    "reason": "before",
                    "role_scores": {"before": 0.7},
                },
                {
                    "media_id": mid,
                    "in_s": 6.0,
                    "out_s": 12.0,
                    "role_hint": "wash",
                    "score": 0.8,
                    "keyframe_path": shots[1].keyframe,
                    "reason": "wash",
                    "role_scores": {"wash": 0.8},
                },
                {
                    "media_id": mid,
                    "in_s": 12.0,
                    "out_s": 18.0,
                    "role_hint": "after",
                    "score": 0.85,
                    "keyframe_path": shots[2].keyframe,
                    "reason": "after",
                    "role_scores": {"after": 0.85},
                },
            ],
        },
    )
    result = editor.highlights_suggest(target_s=20.0, style="reel")
    assert result["ok"] is True
    assert result["style"] == "reel"
    assert result["candidates"]
    assert result["candidates"][0]["duration_s"] <= 22.0
    assert result["candidates"][0]["arc_complete"] is True


def test_arc_order_ok_and_inverted_penalty() -> None:
    ordered = [
        _card("early", "before", in_s=0, out_s=8, score=0.7, captured_at="2024-03-01T10:00:00Z", shoot_day=1),
        _card("mid", "wash", in_s=8, out_s=16, score=0.8, captured_at="2024-03-01T11:00:00Z", shoot_day=1),
        _card("late", "after", in_s=16, out_s=24, score=0.9, captured_at="2024-03-01T12:00:00Z", shoot_day=1),
    ]
    inverted = [
        _card("late", "before", in_s=0, out_s=8, score=0.9, captured_at="2024-03-02T10:00:00Z", shoot_day=2),
        _card("mid", "wash", in_s=8, out_s=16, score=0.85, captured_at="2024-03-01T11:00:00Z", shoot_day=1),
        _card("early", "after", in_s=16, out_s=24, score=0.95, captured_at="2024-03-01T10:00:00Z", shoot_day=1),
    ]
    ok_sheet = build_candidate_sheet(ordered, target_s=24.0, style="process", process_count=1)
    bad_sheet = build_candidate_sheet(inverted, target_s=24.0, style="process", process_count=1)
    assert ok_sheet is not None and bad_sheet is not None
    assert ok_sheet["arc_order_ok"] is True
    assert bad_sheet["arc_order_ok"] is False
    assert "capture-order" in bad_sheet["reason"]
    assert ok_sheet["score"] > bad_sheet["score"]

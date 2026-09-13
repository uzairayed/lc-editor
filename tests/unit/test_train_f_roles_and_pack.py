"""Train F: process role diversity + highlights_suggest arc packing toward target_s."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from lc_editor.analysis.highlights import suggest_highlight_sheets
from lc_editor.analysis.manifest import Shot, ShotMetrics, write_manifest
from lc_editor.analysis.understand import (
    DEFAULT_PROCESS_ROLES,
    best_role_hint,
    card_from_shot,
    write_understand_cache,
)
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
    media_role: str | None = None,
) -> dict:
    card = {
        "media_id": media_id,
        "in_s": in_s,
        "out_s": out_s,
        "role_hint": role,
        "score": score,
        "keyframe_path": f"/tmp/{media_id}_{role}.jpg",
        "reason": f"{role} span",
        "role_scores": {role: score},
        "source": "understand",
    }
    if media_role:
        card["media_role"] = media_role
    return card


def test_silent_detailing_profiles_map_to_story_roles() -> None:
    """Foam/wash/interior/polish/after cues must not collapse to wash/skip_face."""
    roles = list(DEFAULT_PROCESS_ROLES)
    profiles = {
        "before": ShotMetrics(
            motion=0.08, sharpness=0.55, luma_mean=0.28, blur=0.35, luma_spread=0.45, audio_class="silent"
        ),
        "wash": ShotMetrics(
            motion=0.65, sharpness=0.45, luma_mean=0.55, blur=0.3, luma_spread=0.55, audio_class="ambient"
        ),
        "wheel": ShotMetrics(
            motion=0.08, sharpness=0.85, luma_mean=0.45, blur=0.12, luma_spread=0.35, audio_class="silent"
        ),
        "interior": ShotMetrics(
            motion=0.06, sharpness=0.78, luma_mean=0.35, blur=0.15, luma_spread=0.22, audio_class="silent"
        ),
        "after": ShotMetrics(
            motion=0.07, sharpness=0.88, luma_mean=0.78, blur=0.1, luma_spread=0.5, audio_class="silent"
        ),
        "skip_face": ShotMetrics(
            motion=0.05, sharpness=0.4, luma_mean=0.5, blur=0.25, luma_spread=0.7, audio_class="silent"
        ),
        "machine": ShotMetrics(
            motion=0.55, sharpness=0.65, luma_mean=0.5, blur=0.2, luma_spread=0.35, audio_class="ambient"
        ),
    }
    for expected, metrics in profiles.items():
        shot = _shot("m", 0, metrics=metrics, length=2.0)
        got, _ = best_role_hint(shot, roles)
        assert got == expected, f"{expected} profile labeled {got}"


def test_media_role_prior_biases_ambiguous_spans() -> None:
    shot = _shot(
        "m",
        0,
        metrics=ShotMetrics(
            motion=0.35, sharpness=0.5, luma_mean=0.32, blur=0.3, luma_spread=0.4, audio_class="silent"
        ),
        length=3.0,
    )
    roles = list(DEFAULT_PROCESS_ROLES)
    assert best_role_hint(shot, roles, media_role="before")[0] == "before"
    assert best_role_hint(shot, roles, media_role="interior")[0] == "interior"
    card = card_from_shot(shot, roles, media_role="after")
    assert card["media_role"] == "after"


def test_mixed_album_role_hints_are_diverse() -> None:
    """A mixed silent album must surface before/after/interior/wheel, not wash/skip only."""
    roles = list(DEFAULT_PROCESS_ROLES)
    album = [
        ShotMetrics(motion=0.08, sharpness=0.55, luma_mean=0.28, blur=0.35, luma_spread=0.45, audio_class="silent"),
        ShotMetrics(motion=0.65, sharpness=0.45, luma_mean=0.55, blur=0.3, luma_spread=0.55, audio_class="ambient"),
        ShotMetrics(motion=0.08, sharpness=0.85, luma_mean=0.45, blur=0.12, luma_spread=0.35, audio_class="silent"),
        ShotMetrics(motion=0.06, sharpness=0.78, luma_mean=0.35, blur=0.15, luma_spread=0.22, audio_class="silent"),
        ShotMetrics(motion=0.55, sharpness=0.65, luma_mean=0.5, blur=0.2, luma_spread=0.35, audio_class="ambient"),
        ShotMetrics(motion=0.6, sharpness=0.42, luma_mean=0.52, blur=0.28, luma_spread=0.5, audio_class="ambient"),
        ShotMetrics(motion=0.07, sharpness=0.88, luma_mean=0.78, blur=0.1, luma_spread=0.5, audio_class="silent"),
        ShotMetrics(motion=0.05, sharpness=0.4, luma_mean=0.5, blur=0.25, luma_spread=0.7, audio_class="silent"),
    ]
    labels = [best_role_hint(_shot("m", i, metrics=m, length=2.0), roles)[0] for i, m in enumerate(album)]
    counts = Counter(labels)
    assert counts.get("wash", 0) <= 3
    assert counts.get("skip_face", 0) <= 2
    for needed in ("before", "after", "interior", "wheel"):
        assert needed in counts, f"missing {needed} in {counts}"


def test_highlights_pack_complete_arc_near_60s() -> None:
    cards = [
        _card("m063", "before", in_s=0, out_s=8, score=0.7),
        _card("m069", "wash", in_s=0, out_s=8, score=0.8),
        _card("m084", "interior", in_s=0, out_s=8, score=0.75),
        _card("m108", "wheel", in_s=0, out_s=8, score=0.78),
        _card("m123", "machine", in_s=0, out_s=8, score=0.82),
        _card("m070", "wash", in_s=0, out_s=8, score=0.77),
        _card("m071", "engine", in_s=0, out_s=8, score=0.7),
        _card("m072", "wheel", in_s=0, out_s=8, score=0.74),
        _card("m073", "interior", in_s=0, out_s=8, score=0.73),
        _card("m074", "machine", in_s=0, out_s=8, score=0.8),
        _card("m064", "after", in_s=0, out_s=8, score=0.9),
        _card("m117", "hero", in_s=0, out_s=8, score=0.85),
    ]
    ranked = suggest_highlight_sheets(cards, target_s=60.0, style="process")
    assert ranked
    assert any(c["arc_complete"] and 45.0 <= c["duration_s"] <= 70.0 for c in ranked)
    top = ranked[0]
    assert top["arc_complete"] is True
    assert top["beats"][0]["role"] == "before"
    assert top["beats"][-1]["role"] in {"after", "hero"}
    assert "before" in top["arc"] and "after" in top["arc"]
    # Prefer packed complete arcs over thin incomplete engine→wash sheets.
    thin = [
        _card("x", "engine", in_s=0, out_s=8, score=0.99),
        _card("y", "wash", in_s=0, out_s=8, score=0.99),
    ]
    mixed = suggest_highlight_sheets(cards + thin, target_s=60.0, style="process")
    assert mixed[0]["arc_complete"] is True
    assert mixed[0]["duration_s"] >= 45.0


def test_highlights_suggest_target_60_from_cache(editor: Editor, tmp_path: Path) -> None:
    media_ids = []
    for name in ("063", "069", "084", "108", "123", "070", "064", "117"):
        path = touch_media(tmp_path / "src", name)
        editor.import_file(str(path))
        media_ids.append(editor.media[-1].id)

    role_plan = [
        ("before", 0.7, ShotMetrics(motion=0.08, sharpness=0.55, luma_mean=0.28)),
        ("wash", 0.8, ShotMetrics(motion=0.65, sharpness=0.45, luma_mean=0.55, audio_class="ambient")),
        ("interior", 0.75, ShotMetrics(motion=0.06, sharpness=0.78, luma_mean=0.35, luma_spread=0.22)),
        ("wheel", 0.78, ShotMetrics(motion=0.08, sharpness=0.85, luma_mean=0.45, blur=0.12)),
        ("machine", 0.82, ShotMetrics(motion=0.55, sharpness=0.65, audio_class="ambient")),
        ("wash", 0.77, ShotMetrics(motion=0.6, sharpness=0.42, luma_spread=0.5, audio_class="ambient")),
        ("after", 0.9, ShotMetrics(motion=0.07, sharpness=0.88, luma_mean=0.78)),
        ("hero", 0.85, ShotMetrics(motion=0.05, sharpness=0.8, luma_mean=0.55, luma_spread=0.5)),
    ]
    for i, (role, score, metrics) in enumerate(role_plan):
        mid = media_ids[i]
        item = editor.media[i]
        kf = editor.store.keyframes_dir / f"f{i}.jpg"
        kf.write_bytes(b"\xff\xd8\xff\xd9")
        shot = _shot(mid, i, metrics=metrics, keyframe=str(kf), length=8.0)
        write_manifest(editor._manifest_for(item), [shot])
        write_understand_cache(
            editor._understand_for(item),
            {
                "media_id": mid,
                "cards": [
                    {
                        "media_id": mid,
                        "in_s": 0.0,
                        "out_s": 8.0,
                        "role_hint": role,
                        "score": score,
                        "keyframe_path": str(kf),
                        "reason": role,
                        "role_scores": {role: score},
                        "shot_id": shot.id,
                    }
                ],
            },
        )

    version = editor.timeline_get()["timeline_summary"]["version"]
    result = editor.highlights_suggest(target_s=60.0, style="process")
    assert result["ok"] is True
    assert result["suggest_only"] is True
    assert result["auto_export"] is False
    assert result["timeline_summary"]["version"] == version
    assert any(
        c["arc_complete"] is True and 45.0 <= float(c["duration_s"]) <= 70.0
        for c in result["candidates"]
    )

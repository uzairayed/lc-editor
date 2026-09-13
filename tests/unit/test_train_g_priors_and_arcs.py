"""Train G: soft priors + album diversify stop wash monopoly; arcs complete near 60s."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from lc_editor.analysis.highlights import suggest_highlight_sheets
from lc_editor.analysis.manifest import Shot, ShotMetrics, write_manifest
from lc_editor.analysis.understand import (
    DEFAULT_PROCESS_ROLES,
    best_role_hint,
    diversify_process_album,
    filename_role_priors,
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
    media_index: int | None = None,
    role_scores: dict[str, float] | None = None,
) -> dict:
    card = {
        "media_id": media_id,
        "in_s": in_s,
        "out_s": out_s,
        "role_hint": role,
        "score": score,
        "keyframe_path": f"/tmp/{media_id}_{role}.jpg",
        "reason": f"{role} span",
        "role_scores": role_scores
        or {
            "before": 0.3,
            "wash": 0.8,
            "machine": 0.7,
            "engine": 0.65,
            "skip_face": 0.55,
            "interior": 0.4,
            "wheel": 0.42,
            "after": 0.35,
            "hero": 0.3,
        },
        "source": "understand",
        "media_index": media_index,
    }
    return card


def test_filename_priors_map_story_tokens() -> None:
    assert "before" in filename_role_priors(r"C:/clips/day1_before_arrival.mp4")
    assert "after" in filename_role_priors("/media/final_after_reveal.mov")
    assert "interior" in filename_role_priors("cabin_interior_01.mp4")
    assert "wheel" in filename_role_priors("wheel_rim_detail.mp4")


def test_temporal_thirds_and_order_break_wash_bias() -> None:
    """Ambiguous wash-like metrics: early album/third → before, late → after."""
    roles = list(DEFAULT_PROCESS_ROLES)
    washish = ShotMetrics(
        motion=0.55,
        sharpness=0.45,
        luma_mean=0.5,
        blur=0.3,
        luma_spread=0.5,
        audio_class="ambient",
    )
    early = _shot("m0", 0, metrics=washish, in_s=0.0, out_s=4.0)
    late = _shot("m7", 7, metrics=washish, in_s=20.0, out_s=24.0)
    early_role, _ = best_role_hint(
        early,
        roles,
        media_index=0,
        media_count=8,
        media_duration_s=24.0,
        source_path="clip_063.mp4",
    )
    late_role, _ = best_role_hint(
        late,
        roles,
        media_index=7,
        media_count=8,
        media_duration_s=24.0,
        source_path="clip_117.mp4",
    )
    assert early_role == "before", early_role
    assert late_role == "after", late_role


def test_diversify_breaks_wash_skip_monopoly() -> None:
    """FAIL on Train F failure mode: engine/machine/wash/skip only → must diversify."""
    # Mimic the hard fail histogram: lots of wash/skip_face, some engine/machine, zero bookends.
    monopoly = []
    for i in range(8):
        for j, role in enumerate(("wash", "wash", "skip_face", "engine", "machine", "wash")):
            monopoly.append(
                _card(
                    f"m{i:03d}",
                    role,
                    in_s=float(j * 8),
                    out_s=float(j * 8 + 8),
                    score=0.7 + 0.01 * j,
                    media_index=i,
                    role_scores={
                        "before": 0.25,
                        "wash": 0.85,
                        "machine": 0.72,
                        "engine": 0.7,
                        "skip_face": 0.68,
                        "interior": 0.45 if j == 2 else 0.3,
                        "wheel": 0.48 if j == 3 else 0.32,
                        "after": 0.28,
                        "hero": 0.25,
                    },
                )
            )
    roles = Counter(c["role_hint"] for c in monopoly)
    assert roles.get("before", 0) == 0
    assert roles.get("after", 0) == 0
    assert roles.get("interior", 0) == 0 and roles.get("wheel", 0) == 0
    assert roles.get("wash", 0) >= 10

    fixed = diversify_process_album(monopoly)
    counts = Counter(c["role_hint"] for c in fixed)
    assert counts.get("before", 0) >= 1, counts
    assert counts.get("after", 0) >= 1, counts
    assert counts.get("wash", 0) + counts.get("machine", 0) >= 1, counts
    assert counts.get("interior", 0) + counts.get("wheel", 0) >= 1, counts
    # Must not remain a wash/skip_face monopoly.
    assert counts.get("wash", 0) + counts.get("skip_face", 0) < len(fixed)


def test_wash_only_album_packs_complete_arc_near_60s() -> None:
    """Incomplete engine→machine→wash sheets must not win; soft bookends complete the arc."""
    cards = [
        _card("m063", "engine", in_s=0, out_s=8, score=0.9, media_index=0),
        _card("m069", "machine", in_s=0, out_s=8, score=0.88, media_index=1),
        _card("m084", "wash", in_s=0, out_s=8, score=0.86, media_index=2),
        _card("m108", "wash", in_s=0, out_s=8, score=0.84, media_index=3),
        _card("m123", "machine", in_s=0, out_s=8, score=0.83, media_index=4),
        _card("m070", "wash", in_s=0, out_s=8, score=0.82, media_index=5),
        _card("m071", "engine", in_s=0, out_s=8, score=0.8, media_index=6),
        _card("m064", "wash", in_s=0, out_s=8, score=0.78, media_index=7),
    ]
    # Without Train G diversify/bookends this would be arc_complete=false.
    raw_roles = {c["role_hint"] for c in cards}
    assert "before" not in raw_roles and "after" not in raw_roles

    ranked = suggest_highlight_sheets(cards, target_s=60.0, style="process")
    assert ranked
    assert any(c["arc_complete"] and 45.0 <= c["duration_s"] <= 70.0 for c in ranked), [
        (c["arc"], c["arc_complete"], c["duration_s"]) for c in ranked
    ]
    top = ranked[0]
    assert top["arc_complete"] is True
    assert top["beats"][0]["role"] == "before"
    assert top["beats"][-1]["role"] in {"after", "hero"}
    # Not a wash-only padded fake arc.
    process_roles = [b["role"] for b in top["beats"] if b["section"] == "process"]
    assert process_roles, top["arc"]


def test_media_tag_prior_fallback_when_cues_weak() -> None:
    roles = list(DEFAULT_PROCESS_ROLES)
    washish = ShotMetrics(
        motion=0.5, sharpness=0.45, luma_mean=0.48, blur=0.3, luma_spread=0.48, audio_class="ambient"
    )
    shot = _shot("m", 0, metrics=washish, length=3.0)
    assert best_role_hint(shot, roles, media_role="before")[0] == "before"
    assert best_role_hint(shot, roles, media_role="after")[0] == "after"
    assert best_role_hint(shot, roles, media_role="interior")[0] == "interior"


def test_highlights_suggest_from_wash_monopoly_cache(editor: Editor, tmp_path: Path) -> None:
    """End-to-end: wash-monopoly understand cache still yields complete ~60s arc."""
    media_ids = []
    for i, name in enumerate(("063", "069", "084", "108", "123", "070", "064", "117")):
        path = touch_media(tmp_path / "src", name)
        editor.import_file(str(path))
        media_ids.append(editor.media[-1].id)

    # Seed caches with the Train F failure shape (no before/after/interior/wheel).
    fail_roles = ("engine", "machine", "wash", "wash", "machine", "wash", "engine", "wash")
    for i, role in enumerate(fail_roles):
        mid = media_ids[i]
        item = editor.media[i]
        kf = editor.store.keyframes_dir / f"g{i}.jpg"
        kf.write_bytes(b"\xff\xd8\xff\xd9")
        metrics = ShotMetrics(
            motion=0.55, sharpness=0.45, luma_mean=0.5, luma_spread=0.5, audio_class="ambient"
        )
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
                        "score": 0.8,
                        "keyframe_path": str(kf),
                        "reason": role,
                        "role_scores": {role: 0.8},
                        "shot_id": shot.id,
                        "media_index": i,
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
    ), [(c.get("arc"), c.get("arc_complete"), c.get("duration_s")) for c in result["candidates"]]

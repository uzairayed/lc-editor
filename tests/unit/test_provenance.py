from __future__ import annotations

from lc_editor.analysis.provenance import (
    arc_order_issues,
    cluster_shoot_days,
    hints_from_path,
    propose_card,
    uncarded_slot_issues,
)
from lc_editor.app import Editor
from lc_editor.lint.provenance import provenance_warnings
from lc_editor.lint.review import review_warnings
from lc_editor.models import Clip, MediaCard, MediaItem, Timeline
from tests.conftest import touch_media


def _item(
    mid: str,
    captured_at: str | None = None,
    *,
    role: str | None = None,
    shoot_day: int | str | None = None,
    original: str = "clip.mp4",
    card: MediaCard | None = None,
) -> MediaItem:
    return MediaItem(
        id=mid,
        path=f"{mid}.mp4",
        original_path=original,
        captured_at=captured_at,
        role=role,
        shoot_day=shoot_day,
        card=card,
    )


def test_hints_from_path_whole_tokens_only() -> None:
    assert hints_from_path("album/before/clip.mp4").role == "before"
    assert hints_from_path("album/AFTER/hero.mov").role == "after"
    assert hints_from_path("day1/wash/clip.mp4").shoot_day == 1
    assert hints_from_path("day1/wash/clip.mp4").role == "wash"
    assert hints_from_path("d2_interior.mp4").shoot_day == 2
    assert hints_from_path("d2_interior.mp4").role == "interior"
    assert hints_from_path("beforehand/clip.mp4").role is None
    assert hints_from_path("today/clip.mp4").shoot_day is None
    assert hints_from_path("engine-bay.mp4").role == "engine"


def test_cluster_single_file_and_missing_dates() -> None:
    dated = _item("a", "2024-03-02T08:00:00Z")
    bare = _item("b", None)
    clusters, unclustered = cluster_shoot_days([dated, bare])
    assert unclustered == ["b"]
    assert len(clusters) == 1
    assert clusters[0].shoot_day == 1
    assert clusters[0].media_ids == ["a"]


def test_cluster_same_day_within_four_hours() -> None:
    items = [
        _item("a", "2024-03-02T08:00:00Z"),
        _item("b", "2024-03-02T11:00:00Z"),
    ]
    clusters, unclustered = cluster_shoot_days(items)
    assert unclustered == []
    assert len(clusters) == 1
    assert clusters[0].media_ids == ["a", "b"]


def test_cluster_four_hour_gap_and_date_rollover() -> None:
    items = [
        _item("a", "2024-03-02T08:00:00Z"),
        _item("b", "2024-03-02T13:00:01Z"),
        _item("c", "2024-03-03T09:00:00Z"),
    ]
    clusters, _ = cluster_shoot_days(items)
    assert [c.shoot_day for c in clusters] == [1, 2, 3]
    assert clusters[0].media_ids == ["a"]
    assert clusters[1].media_ids == ["b"]
    assert clusters[2].media_ids == ["c"]


def test_arc_order_day_one_after_as_before() -> None:
    """Day-1 polish (after) captured before a later before — the reported swap."""
    issues = arc_order_issues(
        [
            {
                "clip_id": "c_after",
                "media_id": "m_day1_polish",
                "role": "after",
                "captured_at": "2024-03-01T10:00:00Z",
            },
            {
                "clip_id": "c_before",
                "media_id": "m_later_dusty",
                "role": "before",
                "captured_at": "2024-03-02T10:00:00Z",
            },
        ]
    )
    assert issues
    assert any("SPEC-ANA-18" in row and "c_after" in row for row in issues)


def test_arc_order_ok_when_before_is_earlier() -> None:
    issues = arc_order_issues(
        [
            {
                "clip_id": "c1",
                "media_id": "m1",
                "role": "before",
                "captured_at": "2024-03-01T10:00:00Z",
            },
            {
                "clip_id": "c2",
                "media_id": "m2",
                "role": "after",
                "captured_at": "2024-03-01T14:00:00Z",
            },
        ]
    )
    assert issues == []


def test_uncarded_bookend_warning() -> None:
    media = {
        "m1": _item("m1", "2024-03-01T10:00:00Z", role="before"),
    }
    issues = uncarded_slot_issues(
        [{"clip_id": "c1", "media_id": "m1", "role": "before", "captured_at": "2024-03-01T10:00:00Z"}],
        media,
    )
    assert any("SPEC-ANA-19" in row and "c1" in row for row in issues)
    carded = {
        "m1": _item(
            "m1",
            "2024-03-01T10:00:00Z",
            role="before",
            card=MediaCard(role="before", confirmed=True, source="agent"),
        )
    }
    assert uncarded_slot_issues(
        [{"clip_id": "c1", "media_id": "m1", "role": "before", "captured_at": "2024-03-01T10:00:00Z"}],
        carded,
    ) == []


def test_review_warnings_include_day_one_after_swap() -> None:
    media = [
        _item("m_after", "2024-03-01T10:00:00Z", role="after"),
        _item("m_before", "2024-03-02T10:00:00Z", role="before"),
    ]
    timeline = Timeline(
        clips=[
            Clip(id="c_after", media_id="m_after", duration_s=5.0, out_s=5.0),
            Clip(id="c_before", media_id="m_before", duration_s=5.0, out_s=5.0),
        ]
    )
    warns = review_warnings(timeline, media=media)
    assert any("SPEC-ANA-18" in w for w in warns)
    assert any("SPEC-ANA-19" in w for w in warns)


def test_understand_span_resolves_role_when_untagged() -> None:
    media = [
        _item("m_after", "2024-03-01T10:00:00Z"),
        _item("m_before", "2024-03-02T10:00:00Z"),
    ]
    timeline = Timeline(
        clips=[
            Clip(id="c_after", media_id="m_after", duration_s=5.0, out_s=5.0),
            Clip(id="c_before", media_id="m_before", duration_s=5.0, out_s=5.0),
        ]
    )
    spans = {
        "m_after": [{"in_s": 0.0, "out_s": 5.0, "role_hint": "after"}],
        "m_before": [{"in_s": 0.0, "out_s": 5.0, "role_hint": "before"}],
    }
    warns = provenance_warnings(timeline, media, understand_spans=spans)
    assert any("SPEC-ANA-18" in w for w in warns)


def test_propose_questions_on_close_scores_and_contradiction() -> None:
    item = _item("m1", "2024-03-01T10:00:00Z", original="day1/panel.mp4")
    peers = [_item("m2", "2024-03-02T10:00:00Z", role="before")]
    proposal = propose_card(
        item,
        understand_cards=[
            {
                "role_hint": "after",
                "score": 0.62,
                "role_scores": {"after": 0.62, "before": 0.60},
                "reason": "bright payoff",
            }
        ],
        cluster_day=1,
        peers=peers,
    )
    assert proposal["proposed_role"] == "after"
    assert proposal["proposed_day"] == 1
    assert proposal["needs_confirmation"] is True
    assert proposal["question"]
    assert "before or after" in proposal["question"]


def test_import_folder_hints_and_shoot_day_suggest(editor: Editor, tmp_path: Path) -> None:
    inbox = tmp_path / "inbox"
    touch_media(inbox / "before", "panel")
    touch_media(inbox / "day2", "wash")
    imported = editor.import_folder(str(inbox / "before"))
    extra = editor.import_file(str(inbox / "day2" / "wash.mp4"))
    assert imported["ok"] is True
    assert imported.get("hints")
    assert extra.get("hints")
    before_row = imported["media"][0]
    assert before_row["role"] == "before"
    assert before_row["card"]["source"] == "folder"
    assert before_row["card"]["confirmed"] is False
    assert extra["media"]["shoot_day"] == 2

    editor.media = [
        editor.media[0].model_copy(update={"captured_at": "2024-03-01T08:00:00Z", "shoot_day": None}),
        editor.media[1].model_copy(
            update={"captured_at": "2024-03-02T13:00:00Z", "shoot_day": None}
        ),
    ]
    editor._save_media()
    suggested = editor.shoot_day_suggest()
    assert suggested["ok"] is True
    assert len(suggested["clusters"]) == 2
    applied = editor.shoot_day_suggest(apply=True, op_id="day-1")
    assert applied["applied"]
    replay = editor.shoot_day_suggest(apply=True, op_id="day-1")
    assert replay["applied"] == applied["applied"]
    assert all(item.shoot_day is not None for item in editor.media)


def test_old_media_json_loads_without_card(editor: Editor) -> None:
    path = editor._media_index_path()
    path.write_text(
        '[{"id":"m_old","path":"x.mp4","original_path":"x.mp4","kind":"video"}]',
        encoding="utf-8",
    )
    editor._load_media()
    assert editor.media[0].card is None

from __future__ import annotations

from lc_editor.migrate import migrate_timeline_data
from lc_editor.models import SCHEMA_V2, Caption, Clip, Timeline
from lc_editor.ops.layers import add_layer
from lc_editor.ops.timeline import Reject
from lc_editor.models import LayerItem


def test_v1_snapshot_migrates_captions_to_layers() -> None:
    data = {
        "clips": [{"id": "c1", "media_id": "m1", "duration_s": 2.5, "start_s": 0.0}],
        "captions": [
            {
                "id": "t1",
                "clip_id": "c1",
                "text": "Cafe Imran, Gharo",
                "role": "body",
                "y_pct": 0.36,
                "lines": ["Cafe Imran, Gharo"],
                "hold_s": 1.5,
                "enter": "fade",
            }
        ],
        "version": 3,
    }
    timeline = migrate_timeline_data(data)
    assert timeline.schema_version == SCHEMA_V2
    assert timeline.layers
    assert timeline.layers[0].caption_id == "t1"
    assert timeline.layers[0].text == "Cafe Imran, Gharo"


def test_layer_add_rejects_empty_text() -> None:
    timeline = Timeline()
    try:
        add_layer(timeline, LayerItem(id="ly1", kind="text", text=""))
        raise AssertionError("expected reject")
    except Reject as exc:
        assert "text" in str(exc)


def test_existing_clip_contract_survives_v2() -> None:
    timeline = Timeline(clips=[Clip(id="c1", media_id="m1", duration_s=2.0)])
    dumped = timeline.model_dump()
    again = Timeline.model_validate(dumped)
    assert again.clips[0].id == "c1"
    assert again.layers == []
    assert again.music == []

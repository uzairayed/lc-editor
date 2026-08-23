from __future__ import annotations

from pathlib import Path

from lc_editor.app import Editor
from lc_editor.render.effects import compile_effect, validate_effect
from lc_editor.models import EffectInstance
from lc_editor.ops.timeline import Reject


def test_effect_registry_bounds() -> None:
    clean = validate_effect("blur", {"amount": 2.0})
    assert clean["amount"] == 2.0
    try:
        validate_effect("blur", {"amount": 99})
        raise AssertionError("expected reject")
    except Reject:
        pass
    try:
        validate_effect("not_real", {})
        raise AssertionError("expected reject")
    except Reject:
        pass
    try:
        validate_effect("blur", {"filter": "hflip"})
        raise AssertionError("expected reject")
    except Reject:
        pass
    compiled = compile_effect(EffectInstance(id="e", name="blur", params={"amount": 2.0}))
    assert "boxblur" in compiled


def test_layer_and_effect_tools(editor: Editor, media_file: Path) -> None:
    editor.import_file(str(media_file))
    editor.clip_add(media_id=editor.media[-1].id, duration_s=3.0)
    added = editor.layer_add(kind="text", text="Cafe Imran, Gharo", start_s=0.2, duration_s=2.0, motion="slide")
    assert added["ok"] is True
    layer_id = editor.timeline_get()["timeline"]["layers"][-1]["id"]
    moved = editor.layer_transform(layer_id, x=0.5, y=0.4, scale=1.0, opacity=0.9)
    assert moved["ok"] is True
    key = editor.layer_keyframe(layer_id, t_s=0.2, opacity=1.0)
    assert key["ok"] is True
    clip_id = editor.timeline_get()["timeline"]["clips"][0]["id"]
    fx = editor.effect_add(clip_id, "grain", {"amount": 0.2})
    assert fx["ok"] is True
    raw = editor.effect_add(clip_id, "blur", {"filter": "geq"})
    assert raw["ok"] is False
    style = editor.text_style(layer_id, motion="pop")
    assert style["ok"] is True

from __future__ import annotations

from pathlib import Path

from lc_editor.app import Editor


def test_template_list_and_apply(editor: Editor, media_file: Path) -> None:
    listed = editor.template_list()
    assert "editorial" in listed["templates"]
    assert "karachi" in listed["templates"]
    editor.import_file(str(media_file))
    editor.clip_add(media_id=editor.media[-1].id, duration_s=5.0)
    applied = editor.template_apply("editorial", bindings={"hook_text": "City of tombs", "body_text": "2 hours out"})
    assert applied["ok"] is True
    layers = editor.timeline_get()["timeline"]["layers"]
    texts = [layer["text"] for layer in layers]
    assert "City of tombs" in texts
    saved = editor.template_save("my_look")
    assert saved["ok"] is True
    assert Path(saved["path"]).exists()


def test_template_cannot_enable_music(editor: Editor) -> None:
    from lc_editor.ops.templates import apply_template
    from lc_editor.ops.timeline import Reject
    from lc_editor.models import Timeline

    try:
        apply_template(Timeline(), {"id": "bad", "allow_music": True, "layers": []})
        raise AssertionError("expected reject")
    except Reject:
        pass

from __future__ import annotations

from lc_editor.web.server import HTTP_TOOLS, WRITE_TOOLS


def test_spec_ses_09_web_has_no_timeline_mutations() -> None:
    assert "clip_add" not in HTTP_TOOLS
    assert "timeline_reset" not in HTTP_TOOLS
    assert "media_card_confirm" in WRITE_TOOLS
    assert "shot_card_confirm" in WRITE_TOOLS

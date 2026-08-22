from __future__ import annotations

from lc_editor.web.server import start_readonly_server
import inspect


def test_spec_ses_09_web_has_no_mutating_post() -> None:
    source = inspect.getsource(start_readonly_server)
    assert "do_POST" in source
    assert "405" in source
    assert "timeline_reset" not in source
    assert "clip_add" not in source

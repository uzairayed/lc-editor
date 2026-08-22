from __future__ import annotations

import hashlib
from pathlib import Path

from lc_editor.fonts import PACKAGE_FONTS, body_font, title_font


def test_spec_rnd_13_packaged_static_fonts() -> None:
    anton = PACKAGE_FONTS / "Anton-Regular.ttf"
    space = PACKAGE_FONTS / "SpaceGrotesk-Bold.ttf"
    assert anton.exists() and anton.stat().st_size > 10000
    assert space.exists() and space.stat().st_size > 10000
    pins = (PACKAGE_FONTS / "SHA256").read_text(encoding="utf-8")
    assert hashlib.sha256(anton.read_bytes()).hexdigest() in pins
    assert hashlib.sha256(space.read_bytes()).hexdigest() in pins
    assert title_font() == anton
    assert body_font() == space
    assert "[" not in space.name

from __future__ import annotations

from pathlib import Path

from PIL import ImageFont

PACKAGE_FONTS = Path(__file__).resolve().parent / "assets" / "fonts"
USER_FONTS = Path.home() / ".lc-editor" / "fonts"

PREFERRED = {
    "title": ["ClashDisplay-Semibold.ttf", "ClashDisplay-Semibold.otf"],
    "body": ["Satoshi-Bold.ttf", "Satoshi-Bold.otf"],
}

PACKAGED = {
    "title": "Anton-Regular.ttf",
    "body": "SpaceGrotesk-Bold.ttf",
}


def _open(path: Path) -> Path | None:
    if not path.exists():
        return None
    try:
        ImageFont.truetype(str(path), 32)
    except OSError:
        return None
    return path


def _find(names: list[str], folders: list[Path]) -> Path | None:
    for folder in folders:
        for name in names:
            found = _open(folder / name)
            if found:
                return found
    return None


def font_for(role: str) -> Path | None:
    folders = [USER_FONTS, PACKAGE_FONTS]
    preferred = _find(PREFERRED.get(role, []), folders)
    if preferred:
        return preferred
    packaged = PACKAGED.get(role)
    if packaged:
        return _find([packaged], [PACKAGE_FONTS, USER_FONTS])
    return None


def title_font() -> Path | None:
    return font_for("title")


def body_font() -> Path | None:
    return font_for("body")

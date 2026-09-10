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

# Named faces agents can pass to caption_add / caption_edit / text_style / project_set.
FONT_ALIASES = {
    "clash": "title",
    "clash-display": "title",
    "display": "title",
    "title": "title",
    "anton": "title",
    "satoshi": "body",
    "body": "body",
    "space-grotesk": "body",
    "space": "body",
}

FONT_ALIAS_HELP = "clash, satoshi, anton, or space-grotesk"


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


def display_font() -> Path | None:
    """Reel display face: Clash Display when installed, else packaged Anton."""
    return title_font()


def normalize_font(name: str | None) -> str:
    if not name:
        return ""
    key = name.strip().lower().replace("_", "-").replace(" ", "-")
    return key if key in FONT_ALIASES else ""


def resolve_font(name: str | None, *, role: str = "title") -> Path | None:
    key = normalize_font(name)
    if key:
        return font_for(FONT_ALIASES[key])
    return font_for(role if role in ("title", "body") else "body")


def role_for_caption(style: str, role: str, font: str = "") -> str:
    key = normalize_font(font)
    if key:
        return FONT_ALIASES[key]
    if style in ("karaoke", "pop", "card"):
        return "title"
    return role if role in ("title", "body") else "body"


def face_for_caption(style: str, role: str, font: str = "") -> Path | None:
    resolved = role_for_caption(style, role, font)
    if font:
        return resolve_font(font, role=resolved)
    if style in ("karaoke", "pop", "card"):
        return title_font()
    return font_for(resolved)


def font_label(path: Path | None) -> str:
    if path is None:
        return "Anton"
    stem = path.stem.lower()
    if "clash" in stem:
        return "Clash Display"
    if "anton" in stem:
        return "Anton"
    if "satoshi" in stem:
        return "Satoshi"
    if "space" in stem or "grotesk" in stem:
        return "Space Grotesk"
    return path.stem.split("-")[0]

from __future__ import annotations

import hashlib
import urllib.request
from pathlib import Path

FONT_DIR = Path.home() / ".lc-editor" / "fonts"

# OFL fallbacks that may be redistributed. Fontshare faces are fetched when possible
# but never vendored in the wheel.
OFL_FONTS = {
    "title": {
        "filename": "Anton-Regular.ttf",
        "url": "https://github.com/google/fonts/raw/main/ofl/anton/Anton-Regular.ttf",
        "sha256": None,
    },
    "body": {
        "filename": "SpaceGrotesk-Bold.ttf",
        "url": "https://github.com/google/fonts/raw/main/ofl/spacegrotesk/SpaceGrotesk%5Bwght%5D.ttf",
        "sha256": None,
    },
}

PREFERRED = {
    "title": ["ClashDisplay-Semibold.ttf", "ClashDisplay-Semibold.otf"],
    "body": ["Satoshi-Bold.ttf", "Satoshi-Bold.otf"],
}


def _find_existing(names: list[str]) -> Path | None:
    search = [FONT_DIR, Path(__file__).resolve().parent / "assets" / "fonts"]
    for folder in search:
        if not folder.exists():
            continue
        for name in names:
            path = folder / name
            if path.exists():
                return path
    return None


def fetch_ofl(role: str) -> Path | None:
    spec = OFL_FONTS[role]
    FONT_DIR.mkdir(parents=True, exist_ok=True)
    dest = FONT_DIR / spec["filename"]
    if dest.exists():
        return dest
    try:
        urllib.request.urlretrieve(spec["url"], dest)
    except OSError:
        return dest if dest.exists() else None
    if spec["sha256"]:
        digest = hashlib.sha256(dest.read_bytes()).hexdigest()
        if digest != spec["sha256"]:
            dest.unlink(missing_ok=True)
            return None
    return dest if dest.exists() else None


def font_for(role: str) -> Path | None:
    preferred = _find_existing(PREFERRED.get(role, []))
    if preferred:
        return preferred
    ofl = _find_existing([OFL_FONTS[role]["filename"]])
    if ofl:
        return ofl
    return fetch_ofl(role)


def title_font() -> Path | None:
    return font_for("title")


def body_font() -> Path | None:
    return font_for("body")

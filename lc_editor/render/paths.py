from __future__ import annotations

from pathlib import Path


def ffmpeg_path(path: Path | str) -> str:
    s = Path(path).resolve().as_posix()
    return s.replace("\\", "/").replace(":", "\\:").replace("'", "\\'")

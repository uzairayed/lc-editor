from __future__ import annotations

from pathlib import Path


def detect_box(image_path: str | Path, kind: str) -> tuple[float, float, float, float] | None:
    """Cheap local detector on a still / keyframe. No cloud VLM.

    Returns a normalized top-left box ``(x, y, w, h)`` in 0-1 of the image,
    or None when OpenCV is missing or nothing is found.
    """
    if kind not in ("face", "plate"):
        return None
    try:
        import cv2  # type: ignore
    except ImportError:
        return None
    path = Path(image_path)
    if not path.exists() or path.stat().st_size < 32:
        return None
    img = cv2.imread(str(path))
    if img is None:
        return None
    height, width = img.shape[:2]
    if width < 8 or height < 8:
        return None
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    cascade_name = (
        "haarcascade_frontalface_default.xml" if kind == "face" else "haarcascade_russian_plate_number.xml"
    )
    cascade_path = Path(cv2.data.haarcascades) / cascade_name
    if not cascade_path.exists():
        return None
    cascade = cv2.CascadeClassifier(str(cascade_path))
    if cascade.empty():
        return None
    min_size = (max(24, width // 20), max(24, height // 20)) if kind == "face" else (max(40, width // 12), max(12, height // 30))
    hits = cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=4, minSize=min_size)
    if hits is None or len(hits) == 0:
        return None
    # Largest detection; pad slightly so the soft mask covers edges.
    x, y, w, h = max(hits, key=lambda r: int(r[2]) * int(r[3]))
    pad_x = w * 0.12
    pad_y = h * 0.12
    x0 = max(0.0, float(x) - pad_x)
    y0 = max(0.0, float(y) - pad_y)
    x1 = min(float(width), float(x + w) + pad_x)
    y1 = min(float(height), float(y + h) + pad_y)
    nw = max(0.02, (x1 - x0) / width)
    nh = max(0.02, (y1 - y0) / height)
    nx = max(0.0, min(1.0 - nw, x0 / width))
    ny = max(0.0, min(1.0 - nh, y0 / height))
    return (round(nx, 4), round(ny, 4), round(nw, 4), round(nh, 4))

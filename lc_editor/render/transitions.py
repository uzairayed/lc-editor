from __future__ import annotations

from lc_editor.models import CANVAS_H, CANVAS_W, CLOSE_FADE_FRAMES, FPS, PUNCH_FRAMES, PUNCH_ZOOM, WHIP_FRAMES


def whip_filter(frames: int = WHIP_FRAMES, fps: int = FPS) -> str:
    d = frames / fps
    slide = f"{CANVAS_W}*0.3"
    return (
        f"[0:v]scale={CANVAS_W}:{CANVAS_H},setsar=1,fps={fps},format=yuv420p,"
        f"boxblur=8:1,crop={CANVAS_W}:{CANVAS_H}:'min({slide},n*({slide}/{frames}))':0[wout];"
        f"[1:v]scale={CANVAS_W}:{CANVAS_H},setsar=1,fps={fps},format=yuv420p,"
        f"boxblur=8:1,crop={CANVAS_W}:{CANVAS_H}:'{slide}-min({slide},n*({slide}/{frames}))':0[win];"
        f"[wout][win]hstack=inputs=2,crop={CANVAS_W}:{CANVAS_H}:'t/{d}*{CANVAS_W}':0"
    )


def punch_in_filter(frames: int = PUNCH_FRAMES) -> str:
    return (
        f"scale=w='{CANVAS_W}*(1+{PUNCH_ZOOM - 1}*min(1,n/{frames}))':"
        f"h='{CANVAS_H}*(1+{PUNCH_ZOOM - 1}*min(1,n/{frames}))':eval=frame,"
        f"crop={CANVAS_W}:{CANVAS_H}"
    )


def close_fade_filter(total_frames: int, frames: int = CLOSE_FADE_FRAMES) -> str:
    start = max(0, total_frames - frames)
    return f"fade=t=out:s={start}:n={frames}"


def banned_transition(kind: str) -> bool:
    return kind in {
        "wipe",
        "wiperight",
        "wipeleft",
        "wipeup",
        "wipedown",
        "spin",
        "dissolve",
        "fadeblack",
        "star",
        "circleopen",
    }

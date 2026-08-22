from __future__ import annotations

from lc_editor.models import CANVAS_H, CANVAS_W, CLOSE_FADE_FRAMES, FPS, PUNCH_FRAMES, PUNCH_ZOOM, WHIP_FRAMES


def whip_filter(frames: int = WHIP_FRAMES, fps: int = FPS) -> str:
    # blur peaks mid-transition via blend; slide uses smoothstep. Never a wipe preset.
    t = f"(n/{frames})"
    ease = f"(3*pow({t},2)-2*pow({t},3))"
    mix = f"sin(PI*N/{frames})"
    slide = f"{CANVAS_W}*0.3"
    return (
        f"[0:v]scale={CANVAS_W}:{CANVAS_H},setsar=1,fps={fps},format=yuv420p,split[0a][0b];"
        f"[0a]boxblur=1:1[0lo];[0b]boxblur=8:1[0hi];"
        f"[0lo][0hi]blend=all_expr='A*(1-{mix})+B*{mix}',"
        f"crop={CANVAS_W}:{CANVAS_H}:'{slide}*{ease}':0[wout];"
        f"[1:v]scale={CANVAS_W}:{CANVAS_H},setsar=1,fps={fps},format=yuv420p,split[1a][1b];"
        f"[1a]boxblur=1:1[1lo];[1b]boxblur=8:1[1hi];"
        f"[1lo][1hi]blend=all_expr='A*(1-{mix})+B*{mix}',"
        f"crop={CANVAS_W}:{CANVAS_H}:'{slide}*(1-{ease})':0[win];"
        f"[wout][win]hstack=inputs=2,crop={CANVAS_W}:{CANVAS_H}:'{ease}*{CANVAS_W}':0"
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


def flash_filter() -> str:
    return "drawbox=x=0:y=0:w=iw:h=ih:color=0xF6EBD4@0.35:t=fill:enable='lte(n,1)'"


def match_filter() -> str:
    return (
        f"scale=w='iw*(1+0.02*(1-min(1,n/2)))':"
        f"h='ih*(1+0.02*(1-min(1,n/2)))':eval=frame,"
        f"crop={CANVAS_W}:{CANVAS_H}"
    )


def j_cut_video() -> str:
    return "null"


def l_cut_video() -> str:
    return "null"


def transition_video(kind: str) -> str:
    if kind == "whip":
        return whip_filter()
    if kind == "punch":
        return punch_in_filter()
    if kind == "close_fade":
        return close_fade_filter(90)
    if kind == "flash":
        return flash_filter()
    if kind == "match":
        return match_filter()
    if kind == "j_cut":
        return j_cut_video()
    if kind == "l_cut":
        return l_cut_video()
    return "null"


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


def graph_has_wipe(graph: str) -> bool:
    lowered = graph.lower()
    return any(name in lowered for name in ("wiperight", "wipeleft", "circleopen", "slidedown", "slideup"))

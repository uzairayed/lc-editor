from __future__ import annotations

from lc_editor.models import CANVAS_H, CANVAS_W, Clip, LayoutPane, MediaItem
from lc_editor.render.motion import crop_cover

LAYOUT_CELLS: dict[str, list[tuple[int, int, int, int]]] = {
    "stack_v": [(0, 0, CANVAS_W, CANVAS_H // 2), (0, CANVAS_H // 2, CANVAS_W, CANVAS_H // 2)],
    "stack_h": [(0, 0, CANVAS_W // 2, CANVAS_H), (CANVAS_W // 2, 0, CANVAS_W // 2, CANVAS_H)],
    "stack_v3": [
        (0, 0, CANVAS_W, 640),
        (0, 640, CANVAS_W, 640),
        (0, 1280, CANVAS_W, 640),
    ],
    "grid_2x2": [
        (0, 0, CANVAS_W // 2, CANVAS_H // 2),
        (CANVAS_W // 2, 0, CANVAS_W // 2, CANVAS_H // 2),
        (0, CANVAS_H // 2, CANVAS_W // 2, CANVAS_H // 2),
        (CANVAS_W // 2, CANVAS_H // 2, CANVAS_W // 2, CANVAS_H // 2),
    ],
}


def layout_cells(kind: str) -> list[tuple[int, int, int, int]]:
    return LAYOUT_CELLS[kind]


def pane_cell_filter(pane: LayoutPane, media: MediaItem, cell: tuple[int, int, int, int], duration_s: float) -> str:
    _x, _y, w, h = cell
    src_w = media.width or CANVAS_W
    src_h = media.height or CANVAS_H
    cover = crop_cover(src_w, src_h, w, h, pane.focus_x, pane.focus_y)
    dur = max(0.01, duration_s)
    return f"{cover},tpad=stop_mode=clone:stop=-1,trim=duration={dur:.4f},setpts=PTS-STARTPTS"


def stack_join(kind: str, labels: list[str]) -> str:
    if kind == "stack_v":
        return f"{''.join(labels)}vstack=inputs=2[laid]"
    if kind == "stack_h":
        return f"{''.join(labels)}hstack=inputs=2[laid]"
    if kind == "stack_v3":
        return f"{''.join(labels)}vstack=inputs=3[laid]"
    if kind == "grid_2x2":
        return (
            f"{labels[0]}{labels[1]}hstack=inputs=2[ltop];"
            f"{labels[2]}{labels[3]}hstack=inputs=2[lbot];"
            "[ltop][lbot]vstack=inputs=2[laid]"
        )
    raise ValueError(f"unknown layout {kind}")


def layout_filter_complex(
    clip: Clip,
    items: list[MediaItem],
    *,
    still_frame: bool = False,
) -> str:
    kind = clip.layout or "stack_v"
    cells = layout_cells(kind)
    parts: list[str] = []
    labels: list[str] = []
    for i, (pane, item, cell) in enumerate(zip(clip.panes, items, cells, strict=True)):
        label = f"[p{i}]"
        labels.append(label)
        if still_frame:
            _x, _y, w, h = cell
            cover = crop_cover(item.width or CANVAS_W, item.height or CANVAS_H, w, h, pane.focus_x, pane.focus_y)
            parts.append(f"[{i}:v]{cover}{label}")
        else:
            parts.append(f"[{i}:v]{pane_cell_filter(pane, item, cell, clip.duration_s)}{label}")
    parts.append(stack_join(kind, labels))
    return ";".join(parts)

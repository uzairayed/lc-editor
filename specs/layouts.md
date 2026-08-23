# SPEC-LAYO: Multi-clip layouts

A layout is one gapless timeline clip that composites two or more sources into one 1080x1920 frame. It is not multicam and not an overlay layer.

## SPEC-LAYO-01: kinds and pane counts

`layout_add(kind, panes, duration_s?)` appends one clip. `kind` and pane count must match:

| Kind | Panes | Shape |
| --- | --- | --- |
| `stack_v` | 2 | top / bottom, equal (1080x960 each) |
| `stack_h` | 2 | left / right, equal (540x1920 each) |
| `stack_v3` | 3 | three rows (1080x640 each) |
| `grid_2x2` | 4 | quadrants (540x960 each) |

Each pane is `{media_id, in_s?, focus_x?, focus_y?}`. Focus is a cover crop into that cell. Unknown kind, wrong count, missing `media_id`, audio-as-pane, or focus outside `[0, 1]` is `ok: false`.

The new clip's `start_s` follows SPEC-EDIT-01. Duration defaults to the acknowledge floor, capped by the shortest remaining source. A longer `duration_s` freezes a short pane on its last frame.

## SPEC-LAYO-02: one slot

A layout counts as one clip for duration, acknowledge floor, and density. `clip.media_id`, `in_s`, and focus stay in sync with pane 0. Only pane 0 is audible. `clip_gain` / `clip_mute` apply to that audio. Captions bind to the layout clip, not to a pane.

All-still layouts default to `kenburns`. Mixed or all-video layouts default to `none`.

## SPEC-LAYO-03: update and pane edit

`layout_update(clip_id, kind?, panes?)` changes kind or replaces panes. The resulting count must match the kind. `layout_pane(clip_id, index, ...)` edits one pane. `clip_refocus` and `clip_trim` edit pane 0. `clip_set_duration` changes the shared hold.

## SPEC-LAYO-04: clear

`layout_clear(clip_id)` drops the layout and keeps a full-frame clip of pane 0.

## SPEC-LAYO-05: review

Review fails if a layout kind is unknown, pane count is wrong, or a pane references missing media.

## SPEC-LAYO-06: no split

`clip_split` on a layout clip is `ok: false`. Remove and `layout_add` again, or `layout_clear` first.

## SPEC-LAYO-07: render

Each pane cover-crops into its cell, then `vstack` / `hstack` builds the frame. That composite is the clip intermediate. Motion, captions, transitions, and the adjustment layer apply after the stack, same as any other clip.

`preview_stills` writes one JPEG of the stacked midpoint, not pane 0 alone.

## When to use

Two named places, two signs, or two plates that are a list: `stack_v`. Three of that kind: `stack_v3`. Four: `grid_2x2`. Two tall portraits: `stack_h`. A vista or a reveal keeps the whole frame. See `context/scenes/pair.md`.

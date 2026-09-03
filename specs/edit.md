# SPEC-EDIT: Timeline and edit verbs

Source: product spec Edit tools; `instructions.md` structure and length.

The timeline is a gapless sequence. Clip start times are derived as the sum of previous clip durations. There is no gap field and no way to insert silence between clips.

Hard duration cap: **60.00s**. Soft target: **15.00s to 28.00s**.

## SPEC-EDIT-01: no gaps

After every successful mutation, for clips in order:

- `clips[0].start_s == 0.0`
- `clips[i].start_s == sum(clips[j].duration_s for j in 0..i-1)`

A gap (any start that is not the running sum) is illegal and never stored.

## SPEC-EDIT-02: clip_add appends

`clip_add(media_id, in_s=0, out_s=source_duration)` appends a clip. The new clip's `start_s` equals the previous timeline duration.

Worked example: two clips of 2.00s and 3.00s already on the timeline; add a 1.50s clip. New clip `start_s` is **5.00**. Timeline duration is **6.50**.

## SPEC-EDIT-03: clip_remove closes the hole

Removing a middle clip shifts later clips earlier so SPEC-EDIT-01 still holds.

Worked example: clips A=2s, B=3s, C=1s. Remove B. Remaining: A start 0, C start **2.00**. Duration **3.00**.

## SPEC-EDIT-04: clip_reorder

`clip_reorder(clip_id, index)` moves a clip to a new index (0-based). Starts are recomputed.

Worked example: [A=2, B=3, C=1], move C to index 0. Order [C, A, B], starts [0.00, 1.00, 3.00].

## SPEC-EDIT-05: trim

`clip_trim(clip_id, in_s, out_s)` sets source in/out. `duration_s` becomes `out_s - in_s`. Downstream starts shift (ripple by default for duration change). `in_s >= 0`, `out_s > in_s`, `out_s` not past source duration.

## SPEC-EDIT-06: ripple trim

`clip_ripple_trim(clip_id, edge, delta_s)` shortens or lengthens one edge and shifts everything after that clip.

- `edge="in"`: `in_s` moves by `+delta_s` (positive delta shortens from the left).
- `edge="out"`: `out_s` moves by `+delta_s` (positive delta lengthens).

Worked example: [A=2, B=3, C=4]. Ripple trim B out by -1.00. B duration **2.00**. C start **4.00**. Total **8.00**.

## SPEC-EDIT-07: split

`clip_split(clip_id, at_s)` splits at a time relative to the clip start. Two clips share the media; first `out` / second `in` meet at the split point.

Worked example: one 6.00s clip (in 0, out 6). Split at 2.00. First: in 0 out 2 duration 2. Second: in 2 out 6 duration 4.

## SPEC-EDIT-08: set_duration

`clip_set_duration(clip_id, duration_s)` sets timeline duration without speed-ramping.

- Shorter than source span: equivalent to pulling `out_s` in.
- Longer than source span: freeze last frame (video) or extend Ken Burns (still). Never change playback rate.

## SPEC-EDIT-09: fit

`clip_fit(clip_id)` sets clip duration to the required hold of the caption on that clip (SPEC-CAP hold). If no caption, `ok: false`.

## SPEC-EDIT-10: refocus

`clip_refocus(clip_id, x, y)` sets the 9:16 crop center as fractions of source width/height, each in `[0, 1]`. Default crop is centered. Out-of-range is `ok: false`.

## SPEC-EDIT-11: gain and mute

`clip_gain(clip_id, db)` sets gain. `clip_mute(clip_id, muted=true)` sets muted. Mute does not delete the clip.

## SPEC-EDIT-12: motion

Exactly one of `none`, `kenburns` (~106% over the clip), `punch` (100 to 108% over 3 to 4 frames at 30fps), `zoom_in`, `zoom_out`, or `zoom_pair`. Stills default to `kenburns`. A still left on `none` for 3.00s or longer warns: locked still is a slideshow.

`zoom_in` / `zoom_out` / `zoom_pair` use a cubic phone ramp of **1.06–1.14** over **18–42 frames** (0.60–1.40s at 30fps), default 27 frames and 1.10. This is not a 1s+ Ken Burns and not the 4-frame `punch`. Prefer `zoom_pair` so the scale returns to 1.00 on the same clip. `motion_zoom_in` / `motion_zoom_out` remain for one-sided end-card cases.

## SPEC-EDIT-22: when to zoom

`motion_zoom_suggest()` returns per clip `{clip_id, action: "pair"|"punch"|"none", at_s?, reason[]}`. Default is `none`.

Do pair when most of these hold: duration ≥ 3.5s, picture is stable, a payoff inside the clip, face/protect still has margin at 1.10, previous clip was not a pair, at most 3 pairs per 60s. Clip < 2.5s, tight protect, or an opening still Ken Burns: `none`. `review_report` includes `zoom: {pairs, punches, skipped}` and fails a mid-reel `zoom_in` with no out.

## SPEC-EDIT-13: transitions

Legal kinds: `hard`, `whip`, `punch`, `close_fade`, `j_cut`, `l_cut`, `flash`, `match`. See `specs/transitions.md`.

- `hard` is the default between clips. Video stays concat. Audio may acrossfade 8–12 ms.
- `close_fade` is a 4-frame luma fade and is only legal on the last clip.
- Decorated: whip, punch, close_fade, j_cut, l_cut, flash, match.
- More than 3 decorated transitions: mutation succeeds with a warning. `review_report` fails.
- Wipes, spins, cross-dissolves, packs: `ok: false`.

## SPEC-EDIT-14: hard duration cap

A mutation that would make timeline duration greater than **60.00s** is `ok: false` and is not applied.

Worked example: timeline at 60.00s, `clip_add` of a 2.00s shot is rejected. Duration stays **60.00**.

## SPEC-EDIT-15: soft length warnings

After a successful mutation:

- duration `> 28.00`: warning (keep, do not reject)
- duration `< 15.00` and at least one clip: warning (keep)

## SPEC-EDIT-16: idempotent op_id

Every mutation accepts optional `op_id`. Replaying the same `op_id` returns the original result and does not duplicate.

Worked example: `clip_add` with `op_id="a1"` twice yields one clip.

## SPEC-EDIT-17: undo and redo

Undo moves the snapshot pointer back one mutation. Redo moves forward. A new mutation after undo drops the redo branch. `timeline_reset` writes a new snapshot of an empty timeline (undo can restore the previous one).

## SPEC-EDIT-18: stills are clips

An imported still becomes a clip with a duration (default 2.50s) and motion `kenburns`. It is never a static overlay.

## SPEC-EDIT-ACK: acknowledge floor and density

A clip must stay on screen long enough to register. Caption hold is not the same as a picture floor.

- `SHOT_ACK_MIN_S = 2.4` for video on the timeline.
- `STILL_ACK_MIN_S = 2.2` for stills (already above locked-still 1.4s).
- A fragment shorter than the floor is `SPEC-EDIT-ACK-01` and fails `review_report`, unless the clip holds its entire source. A whole-source hold shorter than the floor is a warning, not an error.
- Clip count may not exceed `ceil(duration_s * 16 / 60)` (`SPEC-EDIT-ACK-02`). A 60s reel therefore lands at most 16 clips. Override with `review_report(allow_dense=true)`.
- `shots_rank` drops video shots shorter than `SHOT_ACK_MIN_S`. If that empties the pool, it falls back to all shots with a warning.
- `clip_add` defaults video duration to `SHOT_ACK_MIN_S` (or the whole source if shorter).

## SPEC-EDIT-19: timeline_get is one call

`timeline_get` returns the full JSON timeline in one response, plus `timeline_summary`.

## SPEC-EDIT-20: timeline schema v2

Snapshots store `schema_version`. Missing or `1` loads as v1 and is migrated on read to v2 (layers, music, beat_grid, template_id). The primary `clips` list stays gapless (SPEC-EDIT-01). Overlay video, image, and text live in `layers` with absolute `start_s` / `duration_s` and integer `z`. Existing clip and caption tools keep working.

## SPEC-EDIT-21: layers

`layer_add(kind, start_s, duration_s, media_id?|text?, z?, transform?, style?)` appends a timed overlay. `kind` is `video`, `image`, or `text`. Text layers follow SPEC-CAP (no box, hold, safe zone). `layer_update`, `layer_remove`, `layer_reorder` (z-order), `layer_transform`, and `layer_keyframe` mutate one item. Overlapping layers composite by ascending `z`.

## SPEC-EDIT-22: effects

`effect_add(target, name, params?)` attaches a registry effect to a clip (`target=clip_id`) or layer (`target=layer_id`). Legal names: `blur`, `sharpen`, `glow`, `grain`, `vignette`, `lut`, `color`. Raw ffmpeg filter strings are rejected. `effect_update` / `effect_remove` edit the instance.

## SPEC-EDIT-23: layouts

`layout_add(kind, panes)` appends one clip that shows two or more sources at once. The clip stays on the gapless primary track. Kinds, pane counts, review, and render live in `specs/layouts.md`. `clip_split` on a layout is `ok: false`.

## SPEC-EDIT-24: facecam PiP

`cam_pip(clip_id, x, y, w, h)` crops a rect from the clip's own 16:9 media and pins it as a PiP (default overlay 632:72, ~420 wide, 3px black pad on 1080×1920). Skip when the source already fills 9:16 (`clip_refocus` COVER is enough). `cam_pip_clear` removes it. `cam_pip_suggest` returns a top-right box for 16:9.

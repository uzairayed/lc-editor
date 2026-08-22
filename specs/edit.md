# SPEC-EDIT: Timeline and edit verbs

Source: product spec Edit tools; `instructions.md` structure and length.

The timeline is a gapless sequence. Clip start times are derived as the sum of previous clip durations. There is no gap field and no way to insert silence between clips.

Hard duration cap: **45.00s**. Soft target: **15.00s to 28.00s**.

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

Exactly one of `none`, `kenburns` (~106% over the clip), `punch` (100 to 108% over 3 to 4 frames at 30fps). Stills default to `kenburns`. A still left on `none` for 3.00s or longer warns: locked still is a slideshow.

## SPEC-EDIT-13: transitions

Legal kinds: `hard`, `whip`, `punch`, `close_fade`, `j_cut`, `l_cut`, `flash`, `match`. See `specs/transitions.md`.

- `hard` is the default between clips. Video stays concat. Audio may acrossfade 8–12 ms.
- `close_fade` is a 4-frame luma fade and is only legal on the last clip.
- Decorated: whip, punch, close_fade, j_cut, l_cut, flash, match.
- More than 3 decorated transitions: mutation succeeds with a warning. `review_report` fails.
- Wipes, spins, cross-dissolves, packs: `ok: false`.

## SPEC-EDIT-14: hard duration cap

A mutation that would make timeline duration greater than **45.00s** is `ok: false` and is not applied.

Worked example: timeline at 44.00s, `clip_add` of a 2.00s shot is rejected. Duration stays **44.00**.

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

## SPEC-EDIT-19: timeline_get is one call

`timeline_get` returns the full JSON timeline in one response, plus `timeline_summary`.

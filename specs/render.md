# SPEC-RND: Motion, grade, overlays, filtergraphs

Source: `instructions.md` Transitions, Grade; product spec Motion / Look / Out preview.

Filtergraph builders are pure: params in, filter string out. Golden strings are locked after one hand-check against ffmpeg.

## SPEC-RND-01: kenburns

Ken Burns is a slow zoom of about **106%** over the clip duration (scale 1.00 to 1.06). Applied via `zoompan` or equivalent scale/crop expressions. A still uses the same tool (looped frames + kenburns).

## SPEC-RND-02: punch motion

Punch is a 100 to 108% scale-in over **4 frames** at 30fps (4/30 = 0.133...s), then holds. Not a speed-ramp.

## SPEC-RND-03: whip

Whip is a short directional blur + slide between two clips (about 6 to 10 frames). It is not `xfade=transition=wiperight` or any wipe preset. Golden string is locked in `tests/render/`.

## SPEC-RND-04: close fade

Closer is a **4-frame** luma fade at 30fps on the last clip only (`fade=t=out:n=4` or duration 4/30).

## SPEC-RND-05: hard cut

Hard cut is concat with no xfade and no wipe.

## SPEC-RND-06: captions in the graph

Caption drawtext includes `textfile=`, `expansion=none`, sand fill, stroke, shadow. Never `box=1`. Never inline caption text in the filter string.

## SPEC-RND-07: one grade per project

`grade_preset` sets `motovlog`, `winter_trip`, or `neutral` (or a `.cube` via `grade_set`). A second preset replaces the first; clips do not carry their own LUT name.

## SPEC-RND-08: protect

`grade_protect(clip_id, enabled)` sets a per-clip flag. Protected clips blend the LUT at reduced intensity (0.40) and skip split-tone shadows. Intensity slots: **1.00 / 0.70 / 0.40**.

## SPEC-RND-09: overlays preview vs bake

`overlay_preview` enables IG/TikTok/Shorts chrome and safe-zone guides for preview only. Bake-ins (`series_card`, `location_chip`, `progress`, `end_card`, `social_chrome`) default **off**. `overlay_bake` turns individual bake-ins on only when asked. Export does not burn social chrome unless baked.

## SPEC-RND-10: per-clip cache key

An intermediate file is named by a content hash of that clip's render parameters (media, in/out, motion, crop, grade, captions on that clip). Changing another clip does not invalidate this hash.

## SPEC-RND-11: preview stills

`preview_stills` writes one still per clip (midpoint frame) under the project cache. Does not require a hero encode.

## SPEC-RND-12: one-clip preview

`preview_clip(clip_id)` renders only that clip to a short proxy.

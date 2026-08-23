# SPEC-RND: Motion, grade, overlays, filtergraphs

Source: `instructions.md` Transitions, Grade; product spec Motion / Look / Out preview.

Filtergraph builders are pure: params in, filter string out. Golden strings are locked after one hand-check against ffmpeg.

## SPEC-RND-01: kenburns

Ken Burns is a slow zoom of about **106%** over the clip duration. The zoom uses a **smoothstep ease**, not a linear `1+0.06*on/N`. `motion_kenburns(..., amount=)` may change the end scale. A still uses the same tool (looped frames + kenburns).

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

`grade_protect(clip_id, enabled)` sets a per-clip flag and stores an intensity slot (**1.00 / 0.70 / 0.40**). The LUT itself is applied once on the adjustment layer (SPEC-ADJ), not baked per clip.

## SPEC-RND-09: overlays preview vs bake

`overlay_preview` enables IG/TikTok/Shorts chrome and safe-zone guides for preview only. Bake-ins (`series_card`, `location_chip`, `progress`, `end_card`, `social_chrome`) default **off**. `overlay_bake` turns individual bake-ins on only when asked. Export does not burn social chrome unless baked.

## SPEC-RND-10: per-clip cache key

An intermediate file is named by a content hash of that clip's render parameters (media, in/out, motion, crop, captions, and clip-local filters). Project look (grade, grain, vignette, layer wrap) is not part of the hash. Changing another clip, or changing only the adjustment layer, does not invalidate this hash.

## SPEC-RND-11: preview stills

`preview_stills` writes one still per clip (midpoint frame) under the project directory and returns absolute paths. The files must open as real JPEGs. No base64. Does not require a hero encode.

## SPEC-RND-13: packaged fonts

The wheel ships `Anton-Regular.ttf` and static `SpaceGrotesk-Bold.ttf` (OFL). Clash Display and Satoshi remain optional user overrides. The Space Grotesk file is a 700-weight static face, not a variable `[wght]` file renamed Bold.

## SPEC-RND-14: grade cubes

`neutral`, `winter_trip`, and `motovlog` are 17x17x17 `.cube` files. Neutral stays near identity. Winter cools shadows and slightly warms highlights. Motovlog adds teal shadows and warm mids/highlights. A still rendered through each preset must differ in sampled pixels.

## SPEC-RND-12: one-clip preview

`preview_clip(clip_id)` renders only that clip to a short proxy.

## SPEC-FX: motion extras and look

- `motion_hold` is an alias of `none`. Stills with `none`/`hold` over 1.40s still fail SPEC-CRAFT-05.
- `motion_speed(clip_id, rate)` is video only. Rate must be in **0.85–1.15**. Reject on stills. Never used to fit a caption.
- `fx_grain(amount)` and `fx_vignette(amount)` are 0–1 project-wide and write the adjustment layer. Implemented as light ffmpeg `noise` / `vignette` after concat, not a plugin pack.

## SPEC-ADJ: adjustment layer

Look is a filter on the already-cut timeline: one encode for grade / grain / vignette / LUT / layer wrap. This is not a source proxy (SPEC-SES-05) and not per-clip grade baking.

### What lives on the layer

- Grade / LUT / intensity
- Grain, vignette, wrap
- Optional global fade / end hold
- Optional `eq` / `colorbalance` overrides (replace `lut3d`)

### What stays clip-local

- In/out, motion, punch, whip, flash, match
- Captions (timing is per shot)
- Wind denoise / highpass / gate (needs the source before concat)
- Per-clip registry effects (`blur`, `sharpen`, `glow`)

Do not put denoise on the adjustment layer.

## SPEC-RND-15: compositor

`assemble` compiles one filtergraph: normalize each primary clip, apply two-input whip at those boundaries, concat the rest, overlay `layers` by `z`, draw text (captions and text layers), then the adjustment layer, then one encode. Proxy and hero share the same graph at different resolution and CRF. Music, bed, SFX, ducking, and limiter live on the audio graph.

## SPEC-RND-16: effect registry

Effects compile through `lc_editor.render.effects`. Each name has typed params, bounds, and compatible kinds. Unknown names and raw filter strings are `ok: false`.

## SPEC-RND-17: cache fingerprint

Per-clip cache keys stay clip-local (SPEC-RND-10). The assembled output fingerprint includes clip hashes, transition kinds and neighbors, layer/effect/music ids, template id, and the adjustment layer. Changing a whip neighbor invalidates the assemble cache.

### Shape

- `project.adjustment` holds the layer. Default is enabled and follows `grade_preset`.
- `adjustment_set` writes grade, grain, vignette, wrap, intensity, optional eq/colorbalance, optional fade/end hold. It does not bump timeline version and does not close the export gate.
- `adjustment_clear` disables the layer (no post-concat look).
- `grade_preset`, `grade_set`, `fx_grain`, and `fx_vignette` write the same layer.
- `preview_proxy` and `export` apply the layer as the last video filter after concat.
- Changing only the layer invalidates the assembled output, not per-clip intermediates.
- `fx_wrap(clip_id, "off"|"soft")` is off by default. Soft is a highlight bloom on one or two hero shots.
- No lens-dirt, film-burn, or FX marketplace. No heavy picture denoise by default.

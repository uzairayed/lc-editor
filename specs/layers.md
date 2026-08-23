# SPEC-LAY: Overlay layers and compositing

Source: Production Reel Foundation v2.

The primary video track remains the gapless `clips` list (SPEC-EDIT-01). Overlays are timed `layers` with absolute timeline times.

## SPEC-LAY-01: kinds

`video`, `image`, `text`. Video and image require `media_id`. Text requires `text` and follows SPEC-CAP (no box, hold formula, 22–50% default safe zone).

## SPEC-LAY-02: transform and keyframes

Default transform is center (`x=0.5`, `y=0.5`), `scale=1`, `rotation=0`, `opacity=1`. Keyframes store optional fields plus `ease=linear|smoothstep`. Missing fields hold the previous value. Interpolation is compiled to ffmpeg `overlay` / `rotate` / `colorchannelmixer` expressions.

## SPEC-LAY-03: z-order

Integer `z`. Primary clips render at z=0. Overlays default to z=10. `layer_reorder` changes z only. Equal z uses insertion order.

## SPEC-LAY-04: captions as text layers

`caption_add` also writes a bound text layer (`caption_id` set). Caption edit/move/remove keep that layer in sync. Independent text layers have `caption_id=null` and may use fade/pop/slide/type-on.

## SPEC-LAY-05: review

Review fails if a layer references missing media, has `duration_s <= 0`, sits fully outside the 1080x1920 canvas, or a text layer would emit `box=1`.
